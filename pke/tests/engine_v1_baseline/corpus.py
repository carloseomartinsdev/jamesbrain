"""I12 — Engine v1 development corpus (NOT holdout).

Each case carries expected labels for deterministic characterization.
Live provider evaluation is separate and deselected by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FailureClass = Literal[
    "intent",
    "routing",
    "frame",
    "canonicalization",
    "transport",
    "none",
]

Severity = Literal["S0", "S1", "S2", "S3", "S4"]

Category = Literal[
    "event",
    "state",
    "relation",
    "attribute",
    "measurement",
    "query",
    "correction",
    "temporal",
    "multi_primitive",
    "ambiguity",
    "unknown_concept",
    "conversational",
    "negative",
    "type",
]


@dataclass(frozen=True)
class EngineCase:
    id: str
    utterance: str
    category: Category
    expected_intent: Literal["assert", "query", "correct", "none"] | None
    expected_primitive: (
        Literal["event", "state", "relation", "attribute", "measurement", "type", "unknown", "multi"]
        | None
    )
    notes: str = ""
    failure_watch: FailureClass = "none"
    severity_if_wrong: Severity = "S3"
    expected_safe_abstention: bool = False


def _c(
    id_: str,
    utt: str,
    cat: Category,
    intent: Literal["assert", "query", "correct", "none"] | None,
    prim: (
        Literal["event", "state", "relation", "attribute", "measurement", "type", "unknown", "multi"]
        | None
    ),
    notes: str = "",
    *,
    watch: FailureClass = "none",
    sev: Severity = "S3",
    abstain: bool = False,
) -> EngineCase:
    return EngineCase(id_, utt, cat, intent, prim, notes, watch, sev, abstain)


def build_corpus() -> list[EngineCase]:
    cases: list[EngineCase] = []

    # --- Event >= 30 ---
    events = [
        ("troquei a embreagem ontem", "maintenance/replace"),
        ("troquei a embreagem", "replace"),
        ("consertaram o ar", "repair"),
        ("instalei o aplicativo", "install"),
        ("comprei um notebook", "purchase"),
        ("paguei o aluguel", "payment"),
        ("fui no dentista", "visit"),
        ("tive reunião com o João", "meeting"),
        ("viajei pra SP", "travel"),
        ("revisei o carro", "service"),
        ("inspecionei o telhado", "inspection"),
        ("mandeia mensagem pro Carlos", "communication typo"),
        ("enviei o PDF", "send"),
        ("recebi o contrato", "receive"),
        ("agendei a revisão", "schedule"),
        ("cancelei a consulta", "cancel"),
        ("medi a temperatura", "measure act"),
        ("olhei o tanque", "check"),
        ("troquei de novo a embreagem", "repeated"),
        ("já troquei isso", "already happened"),
        ("vou trocar a embreagem", "planned"),
        ("troquei ideia com o João", "polysemy not physical"),
        ("levei o carro na oficina", "service visit"),
        ("fiz a troca do óleo", "replacement"),
        ("substituí a bateria", "replace"),
        ("consertei a geladeira", "repair"),
        ("comprei pão ontem", "purchase"),
        ("paguei a conta de luz", "payment"),
        ("visitei a mãe", "visit"),
        ("mandei email pro RH", "communication"),
        ("recebi o boleto", "receive"),
        ("marquei exame pra sexta", "schedule"),
        ("desmarquei a viagem", "cancel"),
        ("chequei o odômetro", "check"),
        ("troquei o pneu furado", "replace"),
    ]
    for i, (utt, note) in enumerate(events, 1):
        cases.append(_c(f"EV{i:02d}", utt, "event", "assert", "event", note, watch="routing"))

    # --- State >= 25 ---
    states = [
        ("a porta tava aberta", "open"),
        ("a porta está fechada", "closed"),
        ("o ar tá ligado", "on"),
        ("o ar está desligado", "off"),
        ("tem vaga disponível", "available"),
        ("o quarto tá indisponível", "unavailable"),
        ("a conta tá paga", "paid"),
        ("a fatura está em aberto", "unpaid"),
        ("o plano continua ativo", "active"),
        ("o cadastro tá inativo", "inactive"),
        ("o tanque tá cheio", "full"),
        ("o tanque está vazio", "empty"),
        ("o wifi tá conectado", "connected"),
        ("o wifi está desconectado", "disconnected"),
        ("o carro tá funcionando", "working"),
        ("a geladeira está quebrada", "broken"),
        ("a porta aberta", "open short"),
        ("geladeira quebrada", "broken short"),
        ("ainda está aberto", "still open"),
        ("não está mais aberto", "no longer — may be evolution"),
        ("o sensor está offline", "unavailable-ish"),
        ("a impressora tá ligada", "on"),
        ("a impressora está desligada", "off"),
        ("o serviço está disponível", "available"),
        ("o serviço está indisponível", "unavailable"),
        ("a porta tá fechada agora", "closed now"),
        ("está quebrado", "implicit subject"),
    ]
    for i, (utt, note) in enumerate(states, 1):
        cases.append(_c(f"ST{i:02d}", utt, "state", "assert", "state", note, watch="routing"))

    # --- Relation >= 25 ---
    relations = [
        ("joão trabalha na acme", "works_at"),
        ("joão trabalha lá na acme", "works_at colloquial"),
        ("maria mora em curitiba", "lives_at"),
        ("o carlos tem um corolla", "owns"),
        ("o carro é do joão", "belongs_to"),
        ("sou segurado pela porto", "insured_by"),
        ("sou membro do clube", "member_of"),
        ("ana é casada com pedro", "married_to"),
        ("sou responsável pelo projeto", "responsible_for"),
        ("a empresa fica em sp", "located_at"),
        ("joão não trabalha mais na acme", "termination"),
        ("joão nunca trabalhou na acme", "negation/historical"),
        ("joão trabalhava na acme", "historical"),
        ("acho que joão ainda trabalha lá", "unknown currentness"),
        ("ela trabalha na acme", "pronoun subject"),
        ("trabalho na momsys", "implicit eu"),
        ("o corolla pertence à maria", "belongs_to"),
        ("pedro é dono do apto", "owns"),
        ("ana mora com a mãe", "lives_at-ish"),
        ("sou afiliado ao sindicato", "member_of"),
        ("o seguro é da porto", "insured_by"),
        ("joão é responsável pela equipe", "responsible_for"),
        ("a sede fica no centro", "located_at"),
        ("eles são casados", "married_to"),
        ("não sou mais membro", "termination"),
        ("trabalhava lá ano passado", "historical"),
        ("não trabalha na acme", "negation"),
    ]
    for i, (utt, note) in enumerate(relations, 1):
        cases.append(_c(f"RL{i:02d}", utt, "relation", "assert", "relation", note, watch="routing"))

    # --- Attribute >= 25 ---
    attrs = [
        ("o carro é preto", "color"),
        ("o corolla é prata", "color"),
        ("a casa tem 200 m²", "area descriptive"),
        ("o notebook pesa 1.5 kg", "may be measurement — watch"),
        ("a marca é toyota", "brand"),
        ("modelo corolla 2020", "model"),
        ("meu nome é carlos", "name"),
        ("a placa é abc1d23", "identifier-like"),
        ("capacidade de 64 GB", "capacity"),
        ("é azul marinho", "color refine"),
        ("o carro é um corolla", "classification TYPE watch"),
        ("é um carro", "TYPE"),
        ("rex é um cachorro", "TYPE"),
        ("joão é médico", "occupation — may abstain"),
        ("a parede era azul em 2024", "temporal attribute"),
        ("o civic é azul", "color"),
        ("cor preta", "short"),
        ("é prata", "color short"),
        ("tem 4 portas", "descriptive count"),
        ("é 2020 o ano do carro", "year property"),
        ("marca honda", "brand"),
        ("modelo civic", "model"),
        ("nome fantasia momsys", "name"),
        ("documento tipo pdf", "type-ish"),
        ("é vermelho o carro", "color inverted order"),
        ("mais especificamente azul-marinho", "enrichment"),
        ("prefiro carros azuis", "preference not property"),
        ("o apartamento tem varanda", "facility-like property"),
        ("a CNH é categoria B", "identifier-like descriptive"),
    ]
    for i, (utt, note) in enumerate(attrs, 1):
        prim: Literal["attribute", "type", "unknown"] = "attribute"
        if "é um " in utt or utt.startswith("é um") or "cachorro" in utt:
            prim = "type"
        if "médico" in utt or "prefiro" in utt:
            cases.append(
                _c(
                    f"AT{i:02d}",
                    utt,
                    "attribute",
                    "assert",
                    "unknown",
                    note,
                    watch="canonicalization",
                    abstain=True,
                    sev="S1",
                )
            )
            continue
        cat: Category = "type" if prim == "type" else "attribute"
        cases.append(_c(f"AT{i:02d}", utt, cat, "assert", prim, note, watch="routing"))

    # --- Measurement >= 30 ---
    meas = [
        ("medi e deu 38 graus", "temperature colloquial"),
        ("a temperatura foi 38°C", "temperature"),
        ("o sensor mediu 38°C", "MP5 measurement-only"),
        ("pesava 10 kg", "weight"),
        ("a caixa pesa 10 kg", "weight"),
        ("fico a 12 km", "distance"),
        ("tinha R$2500", "balance"),
        ("o saldo era 2500 reais", "balance"),
        ("20 litros no tanque", "volume"),
        ("bateria em 80%", "percentage"),
        ("contei 5 caixas", "count"),
        ("velocidade 60 km/h", "speed"),
        ("pressão 2 bar", "pressure"),
        ("38 graus", "number+unit alone — watch"),
        ("200 m²", "may be attribute"),
        ("odômetro 125000 km", "odometer"),
        ("medi a temperatura e deu 95°C", "MP1"),
        ("olhei o tanque e ele estava com 20 litros", "MP2"),
        ("pesei a caixa: 10 kg", "MP3"),
        ("consultei o saldo e tinha R$2500", "MP4"),
        ("deu 36 graus", "temperature result"),
        ("tinha 20 L", "volume"),
        ("80 por cento de bateria", "percentage"),
        ("saldo de R$ 100", "currency"),
        ("pesava uns 10 quilos", "approx weight"),
        ("temperatura 36", "number without unit"),
        ("corri 5 km", "distance event-ish"),
        ("pressão arterial 12 por 8", "pressure"),
        ("velocidade média 50", "speed"),
        ("contei de novo: 5", "count repeated"),
        ("medi ontem: 38°C", "temporal measurement"),
        ("a última medição foi 36", "conversational measurement"),
        ("termômetro marcou 37.2°C", "instrument reading"),
        ("balança indicou 72 kg", "instrument reading"),
    ]
    for i, (utt, note) in enumerate(meas, 1):
        prim: Literal["measurement", "multi", "attribute", "unknown"] = "measurement"
        if utt.startswith("medi a temperatura e") or utt.startswith("olhei o tanque") or utt.startswith(
            "pesei a caixa"
        ) or utt.startswith("consultei o saldo"):
            prim = "multi"
        if utt in {"38 graus", "200 m²"}:
            prim = "unknown"
        cases.append(
            _c(
                f"MS{i:02d}",
                utt,
                "multi_primitive" if prim == "multi" else "measurement",
                "assert",
                prim,
                note,
                watch="routing",
                abstain=prim == "unknown",
                sev="S1" if prim == "unknown" else "S3",
            )
        )

    # --- Query >= 40 ---
    queries = [
        ("já troquei isso?", "boolean event"),
        ("quanto tava a temperatura?", "measurement value"),
        ("qual a cor do corolla?", "attribute"),
        ("a porta está aberta?", "state"),
        ("joão trabalha na acme?", "relation boolean"),
        ("eu disse que era azul?", "meta prior"),
        ("troquei a embreagem em 2024?", "event year"),
        ("quando foi a troca?", "temporal event"),
        ("qual era o saldo?", "measurement"),
        ("quantas vezes troquei?", "count"),
        ("está quebrado?", "state"),
        ("ele ainda trabalha lá?", "relation current"),
        ("o que eu falei sobre o corolla?", "meta"),
        ("foi ontem?", "temporal"),
        ("tem medição de temperatura?", "existence"),
        ("última temperatura?", "latest observation"),
        ("temperatura entre 10 e 11?", "range"),
        ("quem é o dono?", "relation"),
        ("onde o joão trabalha?", "relation object"),
        ("o carro é preto?", "attribute proposition"),
        ("já paguei?", "event/state"),
        ("ainda está aberto?", "state"),
        ("não mais trabalha?", "termination query"),
        ("aconteceu em 2024?", "temporal membership"),
        ("quantos litros tinha?", "measurement"),
        ("qual a marca?", "attribute"),
        ("tá ligado o ar?", "state"),
        ("foi em maio?", "partial temporal"),
        ("isso está errado?", "meta-query"),
        ("corrigi isso?", "correction meta"),
        ("tem evidência de azul?", "existence"),
        ("historicamente joão trabalhou?", "historical"),
        ("durante 2024 ele trabalhou?", "held_during"),
        ("a medição mais recente?", "latest"),
        ("agora a temperatura?", "NOW vs current"),
        ("hoje choveu?", "TODAY event"),
        ("semana passada o que rolou?", "range vague"),
        ("o civic ou o corolla é azul?", "ambiguous query"),
        ("ele é preto?", "ambiguous referent"),
        ("quanto deu?", "elliptical measurement"),
        ("já?", "elliptical"),
        ("e a porta?", "elliptical"),
    ]
    for i, (utt, note) in enumerate(queries, 1):
        cases.append(
            _c(
                f"QY{i:02d}",
                utt,
                "query",
                "query",
                None,
                note,
                watch="intent",
                abstain="?" in utt and len(utt) < 8,
                sev="S1",
            )
        )

    # --- Correction >= 25 ---
    corrections = [
        ("corrigindo era 36", "replace measurement"),
        ("corrigindo: o corolla é preto", "replace attribute"),
        ("desconsidere o que eu disse sobre o corolla ser azul", "retract"),
        ("eu me enganei; joão nunca trabalhou lá", "retract relation"),
        ("li errado: eram 36°C", "replace"),
        ("na verdade ele é preto", "may be correction or preference"),
        ("o corolla não é azul", "negation only"),
        ("o corolla é preto", "contradiction only"),
        ("a parede era azul em 2024", "evolution"),
        ("joão não trabalha mais na acme", "termination"),
        ("a porta está fechada agora", "state evolution"),
        ("a temperatura foi 36°C", "new measurement"),
        ("troquei a embreagem de novo", "repeated event"),
        ("eu disse que era azul?", "query"),
        ("corrigindo: foi em 2025", "replace event time"),
        ("desculpa olhei errado; está fechada", "state replace"),
        ("na verdade eu prefiro carros azuis", "not correction"),
        ("tudo que eu falei sobre o corolla estava errado", "proposition-wide unsupported"),
        ("corrigindo ele é preto", "ambiguous target"),
        ("eu estava enganado sobre isso", "retract vague"),
        ("isso estava errado", "retract vague"),
        ("corrigindo o que eu acabei de dizer", "conversational"),
        ("na verdade foi em 2025", "replace time"),
        ("li errado o sensor: 36", "replace"),
        ("desconsidere isso", "retract underspecified"),
        ("corrigindo: era preto e o sensor quebrou", "multi-assertion risk"),
        ("nunca trabalhou na acme", "nunca without correction cue"),
    ]
    for i, (utt, note) in enumerate(corrections, 1):
        intent: Literal["assert", "query", "correct", "none"] = "assert"
        prim = None
        if utt.startswith("corrigindo") or "engan" in utt or "desconsidere" in utt or "li errado" in utt:
            intent = "correct"
        if utt.endswith("?"):
            intent = "query"
        if "não é azul" in utt or utt == "o corolla é preto":
            intent = "assert"
        if "prefiro" in utt:
            intent = "assert"
        cases.append(
            _c(
                f"CR{i:02d}",
                utt,
                "correction",
                intent,
                prim,
                note,
                watch="intent",
                abstain="tudo que eu falei" in utt or utt in {"desconsidere isso", "isso estava errado"},
                sev="S4" if intent == "correct" else "S3",
            )
        )

    # --- Temporal >= 30 (additional dedicated) ---
    temps = [
        ("foi hoje", "hoje"),
        ("foi agora", "agora"),
        ("foi ontem", "ontem"),
        ("vai ser amanhã", "amanhã"),
        ("semana passada", "semana passada"),
        ("mês passado", "mês passado"),
        ("ano passado", "ano passado"),
        ("em 2024", "year"),
        ("em maio", "month"),
        ("na segunda", "weekday"),
        ("há dois meses", "relative"),
        ("já aconteceu", "já"),
        ("ainda não", "ainda"),
        ("não mais", "não mais"),
        ("de novo", "de novo"),
        ("antes da viagem", "antes"),
        ("depois do almoço", "depois"),
        ("recentemente", "vague"),
        ("acho que foi ano passado", "uncertain"),
        ("foi em maio de 2024", "month+year"),
        ("foi em 2024 acho", "uncertain year"),
        ("troquei ontem a embreagem", "event+ontem"),
        ("a porta tava aberta ontem", "state+ontem"),
        ("medi hoje de manhã", "hoje period"),
        ("agora a porta está fechada", "agora state"),
        ("semana que vem", "future week"),
        ("no mês que vem", "future month"),
        ("desde 2020", "since"),
        ("até 2023", "until"),
        ("por volta de 2024", "approx"),
        ("uns dois anos atrás", "approx relative"),
        ("faz tempo", "vague"),
    ]
    for i, (utt, note) in enumerate(temps, 1):
        cases.append(
            _c(
                f"TM{i:02d}",
                utt,
                "temporal",
                "assert",
                "unknown",
                note,
                watch="frame",
                abstain=True,
                sev="S2",
            )
        )

    # --- Multi-primitive extra (>=10 beyond MP1-5 already in measurement) ---
    multi = [
        ("troquei a embreagem e o odômetro estava em 125000 km", "event+meas"),
        ("revisei o carro e medi a temperatura: 90°C", "event+meas"),
        ("paguei a conta e o saldo ficou 100", "event+meas"),
        ("encheu o tanque: 40 litros", "event+meas"),
        ("verifiquei a bateria: 55%", "event+meas"),
        ("pesquei e a balança marcou 2 kg", "event+meas"),
        ("consultei o app: R$300", "event+meas"),
        ("olhei o painel e a velocidade era 80", "event+meas"),
        ("troquei o óleo e anotei 130000 km", "event+meas"),
        ("fiz a medição e deu 37.5", "event+meas"),
        ("o termômetro mostrou 38 e eu anotei", "meas+event order"),
        ("sensor leu 36°C sem eu medir", "measurement-only"),
    ]
    for i, (utt, note) in enumerate(multi, 1):
        prim: Literal["multi", "measurement"] = "measurement" if "sem eu medir" in utt else "multi"
        cases.append(_c(f"MPX{i:02d}", utt, "multi_primitive", "assert", prim, note, watch="routing"))

    # --- Ambiguity >= 25 ---
    amb = [
        ("ele é preto", "pronoun"),
        ("corrigindo: ele é preto", "correction ambiguous"),
        ("essa conta", "underspecified"),
        ("o carro", "which car"),
        ("aquela", "demonstrative"),
        ("isso", "isso"),
        ("o que eu falei", "meta ref"),
        ("a última medição", "recency conversational"),
        ("civic ou corolla?", "choice"),
        ("tá aberto", "what"),
        ("trabalha lá", "where"),
        ("é azul", "subject missing"),
        ("36", "bare number"),
        ("ontem", "bare temporal"),
        ("de novo", "bare"),
        ("não", "bare negation"),
        ("sim o preto", "elliptical"),
        ("o outro", "other"),
        ("aquele lá", "vague"),
        ("a mesma coisa", "anaphora"),
        ("como antes", "anaphora"),
        ("também", "elliptical"),
        ("igual o anterior", "anaphora"),
        ("esse mesmo", "demonstrative"),
        ("lá", "locative vague"),
        ("depois", "temporal vague"),
        ("antes disso", "anaphora"),
    ]
    for i, (utt, note) in enumerate(amb, 1):
        cases.append(
            _c(
                f"AM{i:02d}",
                utt,
                "ambiguity",
                None,
                "unknown",
                note,
                watch="canonicalization",
                abstain=True,
                sev="S0",
            )
        )

    # --- Unknown concepts >= 20 ---
    unk = [
        ("o flibberish quebrou", "unknown noun"),
        ("fiz a zarugagem do motor", "unknown action"),
        ("está zornificado", "unknown state"),
        ("é blorptiano", "unknown attribute"),
        ("medi o quantonium: 3 qx", "unknown dimension"),
        ("trabalha na zxcorp", "unknown org ok entity"),
        ("instalei o snorfle", "unknown object"),
        ("o snorfle está aberto", "unknown entity state"),
        ("sou membro do clã blip", "unknown org"),
        ("cor glórb", "unknown color term"),
        ("unidade em quarbles", "unknown unit"),
        ("fiz o ritual de calibração quântica", "out of ontology"),
        ("está em modo turboflux", "unknown state value"),
        ("relação de mentoria espiritual com X", "gap"),
        ("comprei um hoverbike", "unknown type"),
        ("paguei em mooncoins", "unknown currency"),
        ("a pressão thrak estava alta", "unknown"),
        ("agendei a hiperconsultoria", "unknown event"),
        ("desconectei o neuralink caseiro", "unknown"),
        ("o appliance está em stand-by-z", "unknown"),
        ("é um xerófito", "unknown type"),
        ("troquei o flangulator", "unknown part"),
    ]
    for i, (utt, note) in enumerate(unk, 1):
        cases.append(
            _c(
                f"UK{i:02d}",
                utt,
                "unknown_concept",
                "assert",
                "unknown",
                note,
                watch="canonicalization",
                abstain=True,
                sev="S0",
            )
        )

    # --- Conversational refs ---
    conv = [
        ("isso que eu falei", "isso"),
        ("ele mesmo", "ele"),
        ("ela também", "ela"),
        ("aquele carro", "aquele"),
        ("essa conta aí", "essa"),
        ("o que eu acabei de dizer", "recent utterance"),
        ("a última medição", "last measurement conversational"),
        ("corrigindo o que eu acabei de dizer", "correction+conversation"),
        ("não aquilo", "contrast"),
        ("sim esse", "confirm ref"),
    ]
    for i, (utt, note) in enumerate(conv, 1):
        cases.append(
            _c(
                f"CV{i:02d}",
                utt,
                "conversational",
                None,
                "unknown",
                note,
                watch="frame",
                abstain=True,
                sev="S1",
            )
        )

    # --- Negative / contrastive ---
    neg = [
        ("não troquei a embreagem", "negated event"),
        ("não está aberta", "negated state"),
        ("não trabalha na acme", "negated relation"),
        ("não é preto", "negated attribute"),
        ("não medi nada", "negated measurement"),
        ("não foi em 2024", "negated time"),
        ("não é um carro", "negated type"),
        ("não corrigi", "negated correction meta"),
        ("mas não é azul", "contrast"),
        ("ao contrário: está fechada", "contrast state"),
    ]
    for i, (utt, note) in enumerate(neg, 1):
        cases.append(_c(f"NG{i:02d}", utt, "negative", "assert", None, note, watch="intent", sev="S2"))

    return cases


CORPUS: list[EngineCase] = build_corpus()
