from decimal import Decimal

from actions.sale_manager import discounted_price, money, money_text


def test_discount_20_percent():
    assert discounted_price('100', 20) == Decimal('80.00')


def test_shopify_money_rounding():
    assert discounted_price('79.99', 20) == Decimal('63.99')
    assert discounted_price('19.90', 5) == Decimal('18.91')


def test_money_format():
    assert money('100') == Decimal('100.00')
    assert money_text('8') == '8.00'

class FakeClient:
    def __init__(self):
        self.calls = []

    def rest_request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        class R:
            def json(self):
                return {}
        return R()


def test_apply_variant_payload():
    from actions.sale_manager import apply_variant_discount
    client = FakeClient()
    product = {'title': 'Test Product'}
    variant = {'id': 10, 'sku': 'SKU1', 'price': '100.00', 'compare_at_price': None}
    result = apply_variant_discount(None, client, product, variant, 20, False)
    assert result == 'updated'
    method, path, kwargs = client.calls[0]
    assert method == 'PUT'
    assert path == '/variants/10.json'
    assert kwargs['json']['variant']['price'] == '80.00'
    assert kwargs['json']['variant']['compare_at_price'] == '100.00'


def test_apply_does_not_stack_discount():
    from actions.sale_manager import apply_variant_discount
    client = FakeClient()
    product = {'title': 'Test Product'}
    variant = {'id': 10, 'sku': 'SKU1', 'price': '80.00', 'compare_at_price': '100.00'}
    result = apply_variant_discount(None, client, product, variant, 20, False)
    assert result == 'skipped'
    assert client.calls == []


def test_restore_variant_payload():
    from actions.sale_manager import restore_variant_price
    client = FakeClient()
    product = {'title': 'Test Product'}
    variant = {'id': 10, 'sku': 'SKU1', 'price': '80.00', 'compare_at_price': '100.00'}
    result = restore_variant_price(None, client, product, variant, False)
    assert result == 'updated'
    method, path, kwargs = client.calls[0]
    assert method == 'PUT'
    assert path == '/variants/10.json'
    assert kwargs['json']['variant']['price'] == '100.00'
    assert kwargs['json']['variant']['compare_at_price'] is None
