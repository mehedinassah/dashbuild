from django import template

from core.modules import crud_modules

register = template.Library()


@register.inclusion_tag("core/menu.html")
def crud_menu():
    return {"items": crud_modules()}
