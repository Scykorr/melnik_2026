import pytest

playwright = pytest.importorskip("playwright.sync_api")


@pytest.mark.django_db(transaction=True)
def test_analyst_path(live_server, page):
    page.goto(live_server.url + "/accounts/login/")
    page.fill("input[name=username]", "analyst")
    page.fill("input[name=password]", "Analyst-IAM-2026!")
    page.click("button[type=submit]")
    page.wait_for_url("**/")
    page.click("text=Очередь проверки")
    page.locator("table a").first.click()
    page.select_option("select[name=status]", "in_review")
    page.fill("textarea[name=comment]", "Беру карточку в проверку")
    page.click("text=Записать решение")
    page.select_option("select[name=status]", "confirmed")
    page.fill("textarea[name=comment]", "Событие подтверждено по публикациям")
    page.click("text=Записать решение")
    page.goto(live_server.url + "/reports/")
    assert "ИАМ" in page.content()
