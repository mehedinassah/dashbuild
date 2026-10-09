from django import template

from core.modules import crud_modules

register = template.Library()


@register.inclusion_tag("core/menu.html", takes_context=True)
def crud_menu(context):
    request = context.get("request")
    path = request.path if request else ""
    return {"items": crud_modules(path=path)}
