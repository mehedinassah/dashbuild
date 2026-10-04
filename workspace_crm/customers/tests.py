from django.test import TestCase
from .models import Customer


class CustomerModelTest(TestCase):
    def test_str_returns_name(self):
        customer = Customer.objects.create(
            name="John Doe", email="john@example.com", phone="1234567890"
        )
        self.assertEqual(str(customer), "John Doe")
