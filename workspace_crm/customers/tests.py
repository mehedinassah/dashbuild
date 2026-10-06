from django.test import TestCase
from .models import Customer


class CustomerModelTest(TestCase):
    def test_str_returns_name(self):
        customer = Customer.objects.create(
            name="John Doe", email="john@example.com", phone="1234567890"
        )
        self.assertEqual(str(customer), "John Doe")



class TestCustomerList(TestCase):
    def test_customer_list_order_by_name(self):
        # Create two customers
        Customer.objects.create(name='Zed', email='zed@example.com', phone='1234567890')
        customer_amy = Customer.objects.create(name='Amy', email='amy@example.com', phone='0987654321')

        # Request the list view and check status code
        response = self.client.get('/customers/')
        self.assertEqual(response.status_code, 200)

        # Check 'Amy' appears before 'Zed' in the page content
        self.assertLess(response.content.index(customer_amy.name.encode()), response.content.index('Zed'.encode()))
