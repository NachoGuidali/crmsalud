from django import template

register = template.Library()


@register.filter
def dict_key(d, key):
    """Access a dict value by key in templates: {{ my_dict|dict_key:variable }}"""
    if isinstance(d, dict):
        return d.get(key, '')
    return ''
