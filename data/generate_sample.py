"""Генератор синтетического набора обращений «Вебнефти» для демо и тестов.

Темы и формулировки взяты из примеров кейса; персональные данные вымышлены и
специально вставлены в тексты, чтобы проверять маскирование.
Запуск: python data/generate_sample.py  (детерминирован, seed = 42).
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
RUN_DATE = datetime(2026, 11, 8, 23, 0)
rnd = random.Random(42)

FIO = ["Иванов Пётр Сергеевич", "Смирнова Анна Викторовна", "Кузнецов Олег Иванович",
       "Попова Мария Андреевна", "Соколов Денис Павлович", "Лебедева Ирина Олеговна"]
COMPANIES = ["ООО «Золотая Нива»", "ООО «АгроТранс»", "ООО «СтройБаза»", "ИП Мельников", "ООО «Северный путь»",
             "ООО «ТехАвто»", "ООО «Колос»", "ООО «Логистик-Юг»", "ООО «Ладога-Агро»", "ООО «ВолгаСнаб»"]


def phone() -> str:
    return f"+7 (9{rnd.randint(10, 99)}) {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}"


def inn() -> str:
    return "77" + "".join(str(rnd.randint(0, 9)) for _ in range(8))


def plate() -> str:
    L = "АВЕКМНОРСТУХ"
    return f"{rnd.choice(L)}{rnd.randint(100, 999)}{rnd.choice(L)}{rnd.choice(L)}{rnd.choice([77, 50, 78, 161])}"


# problem_id, last7, prev7, older, clients, type, module, expected, form templates, call templates, image text
PROBLEMS = [
    ("offer_opf", 3, 3, 2, 5, "bug", "offer", "NEW",
     ["При заключении договора выходит договор оферты индивидуальный предприниматель, изменить не удаётся "
      "(мы {company} — общество с ограниченной ответственностью), ОПФ не заполнено. ИНН {inn}.",
      "В договоре оферты стоит ОПФ ИП, хотя мы ООО. Поле не редактируется. Контакт: {phone}."],
     ["Алло, это {fio}, {company}. Заключаем оферту, а там пишет индивидуальный предприниматель, ОПФ не меняется."],
     None),
    ("offer_next", 6, 1, 0, 6, "bug", "offer", "NEW",
     ["При попытке заключения договора оферты, на втором шаге после заполнения данных не реагирует кнопка далее. "
      "Все данные введены, кнопка горит синим, но ни в одном браузере ничего не происходит.",
      "Кнопка «Далее» на втором шаге оферты не нажимается, пробовали Chrome и Яндекс. {fio}, {phone}."],
     ["Добрый день, {fio}. Второй шаг оферты, жму далее — ничего не происходит, кнопка синяя."],
     "Шаг 2 из 4. Кнопка «Далее» активна"),
    ("vehicle_missing", 3, 3, 1, 4, "bug", "vehicles", "UPDATE",
     ["При бронировании в личном кабинете из списка исчезла машина {plate}. Ранее была внесена, сейчас её нет "
      "в справочнике. Новую добавить не получается, выдаёт ошибку, что машина уже внесена.",
      "Пропала машина из справочника ТС, повторно добавить нельзя — «машина уже внесена». Госномер {plate}."],
     ["Здравствуйте, {company}, у нас машина {plate} пропала из списка, добавить заново не даёт, пишет уже внесена."],
     None),
    ("queue_404", 4, 4, 3, 6, "bug", "queue", "NEW",
     ["В личном кабинете на сайте Вебнефть нет возможности забронировать электронную очередь, выходит ошибка 404 "
      "либо пишет, что время не существует.",
      "Не можем забронировать очередь на налив: ошибка 404. Срочно, отгрузка завтра. {phone}"],
     ["Это {fio}. Бронирую очередь, а мне пишет время не существует, а потом вообще 404."],
     "Ошибка 404. Страница не найдена"),
    ("contact_phone", 3, 3, 2, 5, "feature", "orders", "NEW",
     ["Требуется добавить контактный номер телефона в заявку, т. к. номер указанный ранее {phone} недоступен. "
      "На 11.07.2026 назначена отгрузка. Требуется согласование.",
      "Как поменять телефон водителя в заявке на отгрузку? Сами в кабинете изменить не можем. Новый: {phone}."],
     ["Алло, {fio}, нужно в заявке телефон контактный поменять, старый не работает."],
     None),
    ("contract_login", 3, 2, 1, 5, "access", "account", "SKIP",
     ["При регистрации компании при предоставлении документов поступила информация, что договор уже заключен на "
      "данную организацию. Требуется помощь в предоставлении логина и пароля по ранее заключенному договору. ИНН {inn}."],
     ["Здравствуйте, {company}, пишет договор уже заключён, а логина у нас нет. Помогите."],
     None),
    ("sms_code", 2, 3, 1, 4, "bug", "auth", "SKIP",
     ["Не приходит код-смс для восстановления пароля в личном кабинете. Телефон {phone}.",
      "СМС с кодом не приходит уже час, не можем войти. {fio}"],
     ["Мне СМС-код не приходит на восстановление пароля, номер {phone}."],
     None),
    ("documents", 2, 2, 1, 4, "consultation", "documents", "SKIP",
     ["Подскажите, где получить закрывающие документы за октябрь? {company}",
      "Просим выставить счёт на предоплату по договору, ИНН {inn}."],
     ["Добрый день, нужен акт сверки за квартал, {company}."],
     None),
    ("orders_history", 1, 1, 0, 2, "bug", "orders", "SKIP",
     ["Не отображается история заказов в личном кабинете, раздел пустой."],
     ["У нас история заказов не отображается, пусто всё."],
     None),
    ("outage", 2, 0, 0, 2, "incident", "other", "EXCLUDED",
     ["Сайт не открывается, ошибка 502 у всех сотрудников, отгрузки стоят!"],
     ["Сайт не открывается вообще, 502, у всех."],
     None),
]

NOISE = [
    ("Хотим подключить второго пользователя к кабинету, как это сделать?", "account"),
    ("Есть ли скидка при заказе от 10 тонн?", "other"),
    ("Спасибо за помощь в прошлый раз, всё заработало.", "other"),
    ("Подскажите режим работы нефтебазы в праздники.", "other"),
]


def when(bucket: str) -> datetime:
    lo, hi = {"last7": (0, 6), "prev7": (7, 13), "older": (14, 27)}[bucket]
    d = RUN_DATE - timedelta(days=rnd.randint(lo, hi), hours=rnd.randint(1, 12), minutes=rnd.randint(0, 59))
    return d


def main() -> None:
    tickets, media, golden, expected = [], {}, [], {}
    n = 0
    for pid, last7, prev7, older, n_clients, ttype, module, exp, forms, calls, image in PROBLEMS:
        expected[pid] = exp
        clients = rnd.sample([f"c{i:03d}" for i in range(1, 41)], n_clients)
        buckets = ["last7"] * last7 + ["prev7"] * prev7 + ["older"] * older
        for i, b in enumerate(buckets):
            n += 1
            tid = f"T-26-{n:04d}"
            fill = dict(fio=rnd.choice(FIO), company=rnd.choice(COMPANIES), phone=phone(), inn=inn(), plate=plate())
            client = clients[i % n_clients]
            is_call = rnd.random() < 0.4
            t = {"id": tid, "product": "webneft", "channel": "call" if is_call else "form",
                 "created_at": when(b).isoformat(timespec="minutes"), "client_id": client,
                 "text": "", "audio_ref": None, "attachments": []}
            if is_call:
                t["audio_ref"] = f"audio/{tid}.wav"
                media[t["audio_ref"]] = rnd.choice(calls).format(**fill)
            else:
                t["text"] = rnd.choice(forms).format(**fill)
                if image and rnd.random() < 0.5:
                    ref = f"img/{tid}.png"
                    t["attachments"] = [{"kind": "image", "ref": ref}]
                    media[ref] = f"Скриншот экрана: «{image}»"
            tickets.append(t)
            golden.append({"ticket_id": tid, "problem_id": pid, "type": ttype, "module": module})
    for text, module in NOISE:
        n += 1
        tid = f"T-26-{n:04d}"
        tickets.append({"id": tid, "product": "webneft", "channel": "form",
                        "created_at": when("last7").isoformat(timespec="minutes"),
                        "client_id": f"c{rnd.randint(1, 40):03d}", "text": text, "audio_ref": None,
                        "attachments": []})
        golden.append({"ticket_id": tid, "problem_id": f"noise_{tid}", "type": "consultation", "module": module})

    tickets.sort(key=lambda t: t["created_at"])
    (HERE / "sample_tickets.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in tickets) + "\n", encoding="utf-8")
    (HERE / "media_stub.json").write_text(json.dumps(media, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "golden.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in golden) + "\n", encoding="utf-8")
    (HERE / "expected_decisions.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    print(f"{len(tickets)} тикетов, {len(media)} медиа-заглушек")


if __name__ == "__main__":
    main()
