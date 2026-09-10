from jamescore.capabilities.social import INTENT_GREETING, INTENT_THANKS, INTENT_WELLBEING, SocialCapability


def _check(text: str, intent: str, has_task: bool, task_contains: str | None = None) -> None:
    s = SocialCapability()
    c = s.classify(text)
    assert c["intent"] == intent, (text, c)
    assert bool(c["has_task"]) is has_task, (text, c)
    if has_task:
        assert s.should_prefix_social(c) or intent == "NONE"
        if task_contains:
            assert task_contains.lower() in c["task_text"].lower()
        assert not s.is_social_only(c)
    else:
        assert s.is_social_only(c)
        assert s.compose(c["intent"], "Carlos", c["social_text"] or text)


def test_social_positives():
    _check("Bom dia, James.", INTENT_GREETING, False)
    _check("Olá.", INTENT_GREETING, False)
    _check("Tudo bem?", INTENT_WELLBEING, False)
    _check("Obrigado, James.", INTENT_THANKS, False)
    _check("Até mais.", "FAREWELL", False)
    _check("Bom dia, James. Qual é a cor do meu carro?", INTENT_GREETING, True, "cor do meu carro")
    _check("Oi, James. Meu nome é Carlos.", INTENT_GREETING, True, "Meu nome é Carlos")
    _check("Perfeito, obrigado.", INTENT_THANKS, False)
    _check("Tudo bem? Qual é o meu nome?", INTENT_WELLBEING, True, "meu nome")


def test_social_negatives():
    s = SocialCapability()
    n01 = s.classify("Bom dia é uma expressão usada em português.")
    assert not s.is_social_only(n01)
    n02 = s.classify("Carlos me deu bom dia ontem.")
    assert not s.is_social_only(n02)
    n03 = s.classify("Como você está armazenando meu nome?")
    assert not s.is_social_only(n03)
    n04 = s.classify("Obrigado por lembrar que meu carro é vermelho. Qual é o modelo?")
    assert n04["has_task"]
    assert "modelo" in n04["task_text"].lower()
    assert not s.is_social_only(n04)


def test_wellbeing_sober():
    s = SocialCapability()
    for _ in range(12):
        r = s.compose(INTENT_WELLBEING)
        assert "feliz" not in r.lower()
        assert "ótimo" not in r.lower() and "otimo" not in r.lower()


def test_merge_prefix():
    s = SocialCapability()
    assert s.merge_prefix("Bom dia, Carlos.", "Seu carro é vermelho.") == "Bom dia, Carlos. Seu carro é vermelho."
