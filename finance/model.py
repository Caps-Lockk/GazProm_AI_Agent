"""Финансовая модель «Сигнала» (раздел 6 решения): доходная часть и потолок инвестиций.

Расходы по условию кейса не считаются, поэтому результат модели — максимальный
бюджет разработки и внедрения, при котором проект окупается за 3 года
(= приведённая стоимость эффекта за 3 года).

Запуск: python -m finance.model [--rate 0.17] [--salary 100000]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

YEARS = (2027, 2028, 2029)
HOURS_PER_YEAR = 1973          # производственный календарь, 40-часовая неделя (≈ 2026 г.)
INSURANCE = 0.302              # страховые взносы 30% + травматизм 0,2%
WAGE_INDEX = (0.06, 0.05, 0.05)  # индексация зарплат к уровню 2026 г.: +6% в 2027, +5% в 2028 и 2029
RAMP_REPEAT = (0.5, 1.0, 1.0)  # выход на полный эффект: пилот 3 мес. + тиражирование в 2027
RAMP_MANUAL = (0.75, 1.0, 1.0)


@dataclass(frozen=True)
class Scenario:
    name: str
    repeat_share: float     # доля повторяемых обращений в потоке
    fixed_share: float      # доля повторяемых, которую устраняют исправления
    manual_hours: float     # ч/нед на менеджера на ручные выгрузки и анализ


SCENARIOS = (
    Scenario("Пессимистичный", 0.20, 0.15, 0.5),
    Scenario("Базовый", 0.30, 0.20, 1.0),
    Scenario("Оптимистичный", 0.35, 0.25, 2.0),
)


def yearly_effect(s: Scenario, managers: int = 40, salary: float = 100_000) -> list[dict[str, float]]:
    fte_year = salary * (1 + INSURANCE) * 12
    hour = fte_year / HOURS_PER_YEAR
    idx, out = 1.0, []
    for i, year in enumerate(YEARS):
        idx *= 1 + WAGE_INDEX[i]
        repeat = managers * fte_year * idx * s.repeat_share * s.fixed_share * RAMP_REPEAT[i]
        manual = managers * s.manual_hours * 52 * hour * idx * RAMP_MANUAL[i]
        out.append({"year": year, "repeat": repeat, "manual": manual, "total": repeat + manual})
    return out


def present_value(flows: list[float], rate: float) -> float:
    return sum(f / (1 + rate) ** (t + 1) for t, f in enumerate(flows))


def deposit_income(amount: float, rate: float, years: int = 3) -> float:
    """Альтернатива: те же деньги на депозите/в ОФЗ с реинвестированием."""
    return amount * ((1 + rate) ** years - 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=0.17, help="ставка дисконтирования")
    ap.add_argument("--salary", type=float, default=100_000, help="оклад до НДФЛ, ₽/мес")
    ap.add_argument("--managers", type=int, default=40)
    a = ap.parse_args()
    salary = f"{a.salary:,.0f}".replace(",", " ")
    print(f"Ставка {a.rate:.0%}, оклад {salary} ₽, менеджеров {a.managers}\n")
    print(f"{'Сценарий':<16}" + "".join(f"{y:>9}" for y in YEARS) + f"{'Σ 3 года':>10}{'PV':>8}   млн ₽")
    for s in SCENARIOS:
        flows = [y["total"] for y in yearly_effect(s, a.managers, a.salary)]
        pv = present_value(flows, a.rate)
        print(f"{s.name:<16}" + "".join(f"{f / 1e6:>9.2f}" for f in flows)
              + f"{sum(flows) / 1e6:>10.2f}{pv / 1e6:>8.2f}")
    base = [y["total"] for y in yearly_effect(SCENARIOS[1], a.managers, a.salary)]
    print("\nЧувствительность потолка инвестиций (базовый сценарий):")
    for r in (0.13, 0.17, 0.21):
        print(f"  ставка {r:.0%}: {present_value(base, r) / 1e6:.1f} млн ₽")
    ceiling = present_value(base, a.rate)
    print(f"\nАльтернатива: {ceiling / 1e6:.1f} млн ₽ под 13% на 3 года → "
          f"{deposit_income(ceiling, 0.13) / 1e6:.1f} млн ₽ дохода против {sum(base) / 1e6:.1f} млн ₽ эффекта агента")


if __name__ == "__main__":
    main()
