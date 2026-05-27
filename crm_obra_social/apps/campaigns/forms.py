import json

from django import forms
from .models import Campana
from apps.whatsapp.models import PlantillaHSM
from apps.leads.models import Lead, Plan


CAMPO_CHOICES = [
    ('nombre_completo', 'Nombre completo'),
    ('email', 'Email'),
    ('plan', 'Plan'),
    ('localidad', 'Localidad'),
    ('provincia', 'Provincia'),
    ('telefono', 'Teléfono'),
]


class CampanaForm(forms.ModelForm):
    seg_estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los estados')] + Lead.ESTADO_CHOICES,
        label='Estado del lead',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    seg_plan = forms.ModelChoiceField(
        queryset=Plan.objects.filter(activo=True),
        required=False,
        empty_label='Todos los planes',
        label='Plan de interés',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    seg_provincia = forms.CharField(
        required=False, label='Provincia',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    seg_dias_sin_contacto = forms.IntegerField(
        required=False, min_value=1, label='Días sin contacto (mínimo)',
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    variables_mapping_json = forms.CharField(required=False, widget=forms.HiddenInput())
    contactos_ids_json = forms.CharField(required=False, widget=forms.HiddenInput())
    contactos_clientes_ids_json = forms.CharField(required=False, widget=forms.HiddenInput())
    modo_seleccion = forms.ChoiceField(
        choices=[('segmento', 'Por segmento'), ('manual', 'Selección manual')],
        required=False,
        widget=forms.HiddenInput(),
    )
    tipo_destinatario = forms.ChoiceField(
        choices=Campana.TIPO_CHOICES,
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Campana
        fields = ('nombre', 'plantilla', 'fecha_programada')
        widgets = {
            'fecha_programada': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].widget.attrs['class'] = 'form-control'
        self.fields['plantilla'].widget.attrs.update({'class': 'form-select', 'id': 'id_plantilla'})
        self.fields['plantilla'].queryset = PlantillaHSM.objects.filter(activa=True)
        if self.instance and self.instance.filtros_segmento:
            f = self.instance.filtros_segmento
            self.fields['seg_estado'].initial = f.get('estado', '')
            self.fields['seg_provincia'].initial = f.get('provincia', '')
            self.fields['seg_dias_sin_contacto'].initial = f.get('dias_sin_contacto')
            if f.get('plan_id'):
                self.fields['seg_plan'].initial = f['plan_id']
        if self.instance and self.instance.variables_mapping:
            self.fields['variables_mapping_json'].initial = json.dumps(self.instance.variables_mapping)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.filtros_segmento = {}
        if self.cleaned_data.get('seg_estado'):
            instance.filtros_segmento['estado'] = self.cleaned_data['seg_estado']
        if self.cleaned_data.get('seg_plan'):
            instance.filtros_segmento['plan_id'] = self.cleaned_data['seg_plan'].pk
        if self.cleaned_data.get('seg_provincia'):
            instance.filtros_segmento['provincia'] = self.cleaned_data['seg_provincia']
        if self.cleaned_data.get('seg_dias_sin_contacto'):
            instance.filtros_segmento['dias_sin_contacto'] = self.cleaned_data['seg_dias_sin_contacto']

        raw_mapping = self.cleaned_data.get('variables_mapping_json', '')
        try:
            instance.variables_mapping = json.loads(raw_mapping) if raw_mapping else []
        except (json.JSONDecodeError, TypeError):
            instance.variables_mapping = []

        instance.modo_seleccion = self.cleaned_data.get('modo_seleccion') or 'segmento'
        instance.tipo_destinatario = self.cleaned_data.get('tipo_destinatario') or 'leads'

        raw_ids = self.cleaned_data.get('contactos_ids_json', '')
        try:
            ids = json.loads(raw_ids) if raw_ids else []
            instance.contactos_ids = [int(i) for i in ids if str(i).isdigit()]
        except (json.JSONDecodeError, TypeError, ValueError):
            instance.contactos_ids = []

        raw_clientes_ids = self.cleaned_data.get('contactos_clientes_ids_json', '')
        try:
            ids = json.loads(raw_clientes_ids) if raw_clientes_ids else []
            instance.contactos_clientes_ids = [int(i) for i in ids if str(i).isdigit()]
        except (json.JSONDecodeError, TypeError, ValueError):
            instance.contactos_clientes_ids = []

        if commit:
            instance.save()
        return instance
