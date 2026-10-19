# Прослеживаемость требований

Статусы относятся к текущему MVP. Фактические значения T0, T1, K_T, F1, Precision и Recall — «не измерено», пока нет внешнего корпуса и завершённого эксперимента.

| ID | Требование | Модуль | Тест | Приёмка | Статус |
| --- | --- | --- | --- | --- | --- |
| FR-01 | Пять ролей и запрет действий на сервере | accounts, common.mixins, common.permissions | test_api, test_health_and_ui_flow | Оператор не подтверждает событие | сделано |
| FR-02 | Реестр источников с условиями использования | sources | seed_demo | Активный источник требует проверку условий | сделано |
| FR-03 | RSS/Atom, JSON/CSV, ручная ссылка, адаптер API | ingestion | test_exact_dedup, adapters | Официальный API без ключа сеть не вызывает | сделано |
| FR-04 | Точная и смысловая дедупликация | documents.dedup, documents.services | test_exact_dedup, test_reprint | Повтор не создаёт вторую запись | сделано |
| FR-05 | Состояния события и комментарий решения | events.services | test_event_transitions | Недопустимый переход отвергается | сделано |
| FR-06 | ИПА только по подтверждённым событиям | analytics.formula, analytics.services | test_index_edges | Неподтверждённое событие не входит в компоненты | сделано |
| FR-07 | Неизменяемый ИАМ и экспорт | reports | test_report_is_immutable | Повторное изменение утверждённой версии даёт отказ | сделано |
| FR-08 | Аудит без полного текста | audit.services | test_delete_recomputes | В журнале удаления нет текста публикации | сделано |
| FR-09 | API, фильтры, предел страницы, request_id | common.api | test_api_filters | page_size ограничен 100 | сделано |
| FR-10 | Защита ручного URL от SSRF | common.ssrf | test_ssrf | Частный адрес и редирект на него блокируются | сделано |
| FR-11 | Протокол T0/T1 без вымышленных цифр | experiments | test_labor_and_effect | Пустая база даёт «не измерено» | сделано |
| FR-12 | Нет персональных профилей в выдаче | documents.services, serializers | test_html_is_cleaned, test_api | Поле author не сохраняется и не отдаётся | сделано |
| NFR-01 | Argon2, CSRF, CSP и HSTS в production | settings | просмотр production.py | Production не стартует со стандартным ключом | сделано |
| NFR-02 | /health/live, /health/ready, метрики | common.health, common.metrics | test_health_and_ui_flow | Оба адреса отвечают | сделано |
