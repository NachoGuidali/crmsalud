from django import forms
from django.forms import inlineformset_factory

from .models import Cotizacion, IntegranteFamiliar


class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ('lead', 'plan', 'cantidad_integrantes', 'monto_mensual', 'notas', 'status')
        widgets = {
            'notas': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, lead=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.leads.models import Plan
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.Select, forms.Textarea)):
                field.widget.attrs['class'] = 'form-control'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
        if lead:
            self.fields['lead'].initial = lead
            self.fields['lead'].widget = forms.HiddenInput()
        self.fields['plan'].queryset = Plan.objects.filter(activo=True)


class IntegranteForm(forms.ModelForm):
    class Meta:
        model = IntegranteFamiliar
        fields = ('nombre', 'dni', 'fecha_nacimiento', 'parentesco')
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.Select, forms.DateInput)):
                field.widget.attrs['class'] = 'form-control'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'


IntegranteFormSet = inlineformset_factory(
    Cotizacion, IntegranteFamiliar,
    form=IntegranteForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
