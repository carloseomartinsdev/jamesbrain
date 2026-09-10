from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from pke.domain import (
    DayPeriod,
    EventStatus,
    Recurrence,
    RelativeDay,
    TimePrecision,
    UserContext,
    WeekdayPolicy,
)
from pke.interpretation import IrTime
from pke.resolution import (
    ImpossibleTimeError,
    InsufficientTemporalContextError,
    InvalidTimezoneError,
    TemporalConflictError,
    TemporalContext,
    TemporalResolver,
)

FORTALEZA = ZoneInfo("America/Fortaleza")
# terça-feira 01/09/2026 15:00 em Fortaleza
REF = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
THURSDAY = 3


def _ctx(
    *,
    status: EventStatus | None = None,
    reference_at: dt.datetime | None = REF,
    timezone: str = "America/Fortaleza",
) -> TemporalContext:
    return TemporalContext(
        user=UserContext(user_id="local", timezone=timezone, now=None),
        event_status=status,
        reference_at=reference_at,
    )


def _resolve(ir: IrTime, ctx: TemporalContext | None = None):
    return TemporalResolver().resolve(ir, ctx or _ctx()).calendar


def test_hoje() -> None:
    value = _resolve(IrTime(original_text="hoje", relative_day=RelativeDay.TODAY))
    assert value.date == dt.date(2026, 9, 1)
    assert value.resolution_rule == "relative.today"
    assert value.timezone == "America/Fortaleza"


def test_ontem() -> None:
    value = _resolve(IrTime(original_text="ontem", relative_day=RelativeDay.YESTERDAY))
    assert value.date == dt.date(2026, 8, 31)


def test_amanha() -> None:
    value = _resolve(IrTime(original_text="amanhã", relative_day=RelativeDay.TOMORROW))
    assert value.date == dt.date(2026, 9, 2)


def test_proxima_quinta() -> None:
    value = _resolve(
        IrTime(
            original_text="próxima quinta",
            weekday=THURSDAY,
            weekday_policy=WeekdayPolicy.NEXT,
        )
    )
    assert value.date == dt.date(2026, 9, 3)
    assert value.resolution_rule == "weekday.next"


def test_quinta_contexto_futuro() -> None:
    value = _resolve(
        IrTime(
            original_text="quinta",
            weekday=THURSDAY,
            weekday_policy=WeekdayPolicy.FROM_EVENT_STATUS,
        ),
        _ctx(status=EventStatus.SCHEDULED),
    )
    assert value.date == dt.date(2026, 9, 3)
    assert value.resolution_rule == "weekday.from_event_status.scheduled"


def test_quinta_contexto_passado() -> None:
    value = _resolve(
        IrTime(
            original_text="quinta",
            weekday=THURSDAY,
            weekday_policy=WeekdayPolicy.FROM_EVENT_STATUS,
        ),
        _ctx(status=EventStatus.COMPLETED),
    )
    assert value.date == dt.date(2026, 8, 27)
    assert value.resolution_rule == "weekday.from_event_status.completed"


def test_data_absoluta() -> None:
    value = _resolve(IrTime(original_text="10/09/2026", date=dt.date(2026, 9, 10)))
    assert value.date == dt.date(2026, 9, 10)
    assert value.time_of_day is None
    assert value.precision is TimePrecision.DAY


def test_data_e_horario() -> None:
    value = _resolve(
        IrTime(
            original_text="quinta às 15h",
            date=dt.date(2026, 9, 3),
            time_of_day=dt.time(15, 0),
        )
    )
    assert value.instant == dt.datetime(2026, 9, 3, 15, 0, tzinfo=FORTALEZA)
    assert value.precision is TimePrecision.MINUTE


def test_timezone_diferente() -> None:
    value = _resolve(
        IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
        _ctx(timezone="Asia/Tokyo"),
    )
    assert value.timezone == "Asia/Tokyo"
    assert value.date == dt.date(2026, 9, 2)


def test_mudanca_de_dia_por_timezone() -> None:
    utc_late = dt.datetime(2026, 9, 2, 2, 0, tzinfo=dt.UTC)
    forteza = _resolve(
        IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
        _ctx(reference_at=utc_late, timezone="America/Fortaleza"),
    )
    tokyo = _resolve(
        IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
        _ctx(reference_at=utc_late, timezone="Asia/Tokyo"),
    )
    assert forteza.date == dt.date(2026, 9, 1)
    assert tokyo.date == dt.date(2026, 9, 2)


def test_recorrencia_mensal_dia_10() -> None:
    value = _resolve(
        IrTime(
            original_text="todo dia 10",
            recurrence=Recurrence(freq="monthly", by_monthday=10),
        )
    )
    assert value.recurrence is not None
    assert value.recurrence.by_monthday == 10
    assert value.precision is TimePrecision.RECURRING
    assert value.resolution_rule == "recurrence.monthly_by_monthday"


def test_texto_original_e_reference_at_preservados() -> None:
    ir = IrTime(original_text="quinta-feira", weekday=THURSDAY, weekday_policy=WeekdayPolicy.NEXT)
    value = _resolve(ir)
    assert value.original_text == "quinta-feira"
    assert value.reference_at == REF
    assert value.reference_timezone == "America/Fortaleza"


def test_precisao_aproximada() -> None:
    value = _resolve(
        IrTime(
            original_text="uns dias atrás",
            relative_day=RelativeDay.YESTERDAY,
            precision=TimePrecision.APPROX_DAY,
        )
    )
    assert value.precision is TimePrecision.APPROX_DAY
    assert value.confidence is not None
    assert value.confidence.qualifier.value == "approximately"


def test_periodo_do_dia_nao_inventa_horario() -> None:
    value = _resolve(
        IrTime(
            original_text="quinta de manhã",
            weekday=THURSDAY,
            weekday_policy=WeekdayPolicy.NEXT,
            day_period=DayPeriod.MORNING,
        )
    )
    assert value.date == dt.date(2026, 9, 3)
    assert value.day_period is DayPeriod.MORNING
    assert value.time_of_day is None
    assert value.instant is None
    assert value.precision is TimePrecision.DAY_PERIOD


def test_conflito_temporal_rejeitado() -> None:
    with pytest.raises(TemporalConflictError):
        _resolve(
            IrTime(
                original_text="hoje",
                relative_day=RelativeDay.TODAY,
                date=dt.date(2026, 9, 10),
            )
        )


def test_contexto_insuficiente_rejeitado() -> None:
    resolver = TemporalResolver()
    with pytest.raises(InsufficientTemporalContextError):
        resolver.resolve(
            IrTime(original_text="quinta", weekday=THURSDAY),
            _ctx(status=None),
        )
    with pytest.raises(InsufficientTemporalContextError):
        resolver.resolve(
            IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
            TemporalContext(user=UserContext(user_id="x"), reference_at=None),
        )
    with pytest.raises(InsufficientTemporalContextError):
        resolver.resolve(IrTime(original_text="às 15h", time_of_day=dt.time(15, 0)), _ctx())
    with pytest.raises(InsufficientTemporalContextError):
        resolver.resolve(IrTime(original_text="sem nada"), _ctx())
    with pytest.raises(InsufficientTemporalContextError):
        resolver.resolve(
            IrTime(original_text="todo mês", recurrence=Recurrence(freq="monthly")),
            _ctx(),
        )


def test_timezone_invalido() -> None:
    with pytest.raises(InvalidTimezoneError):
        TemporalResolver().resolve(
            IrTime(original_text="hoje", relative_day=RelativeDay.TODAY, timezone="Marte/Base"),
            _ctx(),
        )


def test_intervalo_invertido_impossivel() -> None:
    with pytest.raises(ImpossibleTimeError):
        _resolve(
            IrTime(
                original_text="intervalo",
                period_start=dt.datetime(2026, 9, 10, 12, 0),
                period_end=dt.datetime(2026, 9, 1, 12, 0),
            )
        )


def test_nao_usa_relogio_da_maquina() -> None:
    ctx = TemporalContext(
        user=UserContext(user_id="x", now=None),
        reference_at=dt.datetime(2020, 1, 15, 8, 0, tzinfo=FORTALEZA),
    )
    value = TemporalResolver().resolve(
        IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
        ctx,
    ).calendar
    assert value.date == dt.date(2020, 1, 15)
    assert value.reference_at == ctx.reference_at
