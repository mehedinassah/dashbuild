"""Helpers for generated tests: build valid sample records for any model."""
import itertools
from decimal import Decimal

from django.db import models

_counter = itertools.count(1)


def sample_value(field, n):
    if isinstance(field, models.ForeignKey):
        return make_instance(field.related_model)
    if isinstance(field, models.BooleanField):
        return True
    if isinstance(field, models.DecimalField):
        return Decimal(n)
    if isinstance(field, models.IntegerField):
        return n
    if isinstance(field, models.DateField):
        return "2026-01-15"
    if isinstance(field, models.EmailField):
        return f"sample{n}@example.com"
    if isinstance(field, models.TextField):
        return f"Some text {n}"
    return f"Sample {n}"


def make_instance(model, **overrides):
    n = next(_counter)
    data = {}
    for field in model._meta.concrete_fields:
        if not field.primary_key:
            data[field.name] = sample_value(field, n)
    data.update(overrides)
    return model.objects.create(**data)


def post_data(model, **overrides):
    n = next(_counter)
    data = {}
    for field in model._meta.concrete_fields:
        if field.primary_key:
            continue
        if isinstance(field, models.ForeignKey):
            data[field.name] = make_instance(field.related_model).pk
        elif isinstance(field, models.BooleanField):
            data[field.name] = "on"
        else:
            data[field.name] = sample_value(field, n)
    data.update(overrides)
    return data
