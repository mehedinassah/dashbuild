from django.test import TestCase
from django.urls import reverse

from core.factories import make_instance, post_data

from .models import Sale

LABEL = "number"


class SaleCrudTests(TestCase):
    def test_str_is_the_first_field(self):
        item = make_instance(Sale)
        self.assertEqual(str(item), str(getattr(item, LABEL)))

    def test_list_page_shows_items(self):
        item = make_instance(Sale)
        response = self.client.get(reverse("sales:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, getattr(item, LABEL))

    def test_search_filters_items(self):
        make_instance(Sale, **{LABEL: "Alpha thing"})
        make_instance(Sale, **{LABEL: "Beta thing"})
        response = self.client.get(reverse("sales:list"), {"q": "alp"})
        self.assertContains(response, "Alpha thing")
        self.assertNotContains(response, "Beta thing")

    def test_create(self):
        response = self.client.post(reverse("sales:create"), post_data(Sale))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.count(), 1)

    def test_update(self):
        item = make_instance(Sale)
        data = post_data(Sale, **{LABEL: "Changed"})
        response = self.client.post(reverse("sales:update", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(str(item), "Changed")

    def test_delete(self):
        item = make_instance(Sale)
        response = self.client.post(reverse("sales:delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.count(), 0)
