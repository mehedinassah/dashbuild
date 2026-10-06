from django.test import TestCase
from django.urls import reverse

from .models import Product

LABEL = "name"

SAMPLE = {
    "name": "Sample",
    "sku": "Sample",
    "price": "9.99",
    "stock": 5,
}

POST = {
    "name": "Sample",
    "sku": "Sample",
    "price": "9.99",
    "stock": "5",
}


class ProductCrudTests(TestCase):
    def make(self, **extra):
        data = dict(SAMPLE)
        data.update(extra)
        return Product.objects.create(**data)

    def test_str_is_the_first_field(self):
        item = self.make()
        self.assertEqual(str(item), SAMPLE[LABEL])

    def test_list_page_shows_items(self):
        self.make()
        response = self.client.get(reverse("products:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SAMPLE[LABEL])

    def test_search_filters_items(self):
        self.make(**{LABEL: "Alpha thing"})
        self.make(**{LABEL: "Beta thing"})
        response = self.client.get(reverse("products:list"), {"q": "alp"})
        self.assertContains(response, "Alpha thing")
        self.assertNotContains(response, "Beta thing")

    def test_create(self):
        response = self.client.post(reverse("products:create"), POST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), 1)

    def test_update(self):
        item = self.make()
        data = dict(POST)
        data[LABEL] = "Changed"
        response = self.client.post(reverse("products:update", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(str(item), "Changed")

    def test_delete(self):
        item = self.make()
        response = self.client.post(reverse("products:delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), 0)
