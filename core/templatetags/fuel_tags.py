from django import template

from core.services import fuel_product_icon, fuel_product_kind


register = template.Library()


@register.inclusion_tag("core/_fuel_pill.html")
def fuel_pill(product_name):
    """Render the shared fuel label used across the EKO UI."""
    return {
        "fuel_name": product_name,
        "fuel_kind": fuel_product_kind(product_name),
        "fuel_icon": fuel_product_icon(product_name),
    }
