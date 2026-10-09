from django.test import TestCase
from django.urls import reverse

from core.factories import make_instance, post_data

from .models import SaleItem

LABEL = "description"


class SaleItemCrudTests(TestCase):
    def test_str_is_the_first_field(self):
        item = make_instance(SaleItem)
        self.assertEqual(str(item), str(getattr(item, LABEL)))

    def test_list_page_shows_items(self):
        item = make_instance(SaleItem)
        response = self.client.get(reverse("saleitems:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, getattr(item, LABEL))

    def test_search_filters_items(self):
        make_instance(SaleItem, **{LABEL: "Alpha thing"})
        make_instance(SaleItem, **{LABEL: "Beta thing"})
        response = self.client.get(reverse("saleitems:list"), {"q": "alp"})
        self.assertContains(response, "Alpha thing")
        self.assertNotContains(response, "Beta thing")

    def test_create(self):
        response = self.client.post(reverse("saleitems:create"), post_data(SaleItem))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SaleItem.objects.count(), 1)

    def test_update(self):
        item = make_instance(SaleItem)
        data = post_data(SaleItem, **{LABEL: "Changed"})
        response = self.client.post(reverse("saleitems:update", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(str(item), "Changed")

    def test_delete(self):
        item = make_instance(SaleItem)
        response = self.client.post(reverse("saleitems:delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SaleItem.objects.count(), 0)
