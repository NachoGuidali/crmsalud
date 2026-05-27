from django import forms
from django.core.exceptions import ValidationError
from apps.leads.models import Plan
from .models import Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            'nombre_completo', 'dni', 'fecha_nacimiento', 'telefono', 'email',
            'localidad', 'provincia', 'plan', 'numero_afiliado', 'grupo_familiar',
            'agente', 'notas',
        ]
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notas': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.Select, forms.Textarea, forms.DateInput)):
                field.widget.attrs['class'] = 'form-control'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
        self.fields['plan'].queryset = Plan.objects.filter(activo=True)
        if user and not user.can_see_all_leads:
            self.fields.pop('agente', None)

    def clean_dni(self):
        dni = self.cleaned_data.get('dni', '').strip()
        if not dni:
            return dni
        qs = Cliente.objects.filter(dni=dni)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            dup = qs.first()
            raise ValidationError(f'Ya existe un cliente con DNI {dni}: {dup.nombre_completo}.')
        from apps.leads.models import Lead
        dup_l = Lead.objects.filter(dni=dni).first()
        if dup_l:
            raise ValidationError(f'Ya existe un lead con DNI {dni}: {dup_l.nombre_completo}. Buscalo en Leads.')
        return dni

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono', '').strip()
        if not telefono:
            return telefono
        qs = Cliente.objects.filter(telefono=telefono)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            dup = qs.first()
            raise ValidationError(f'Ya existe un cliente con ese teléfono: {dup.nombre_completo}.')
        from apps.leads.models import Lead
        dup_l = Lead.objects.filter(telefono=telefono).first()
        if dup_l:
            raise ValidationError(f'Ya existe un lead con ese teléfono: {dup_l.nombre_completo}. Buscalo en Leads.')
        return telefono


class ClienteImportForm(forms.Form):
    archivo = forms.FileField(
        label='Archivo de clientes',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv,.xlsx,.xls'}),
        help_text='CSV o Excel (.xlsx). Columnas: nombre_completo, dni, telefono, email, plan, numero_afiliado, localidad, provincia, grupo_familiar, notas.',
    )
    actualizar_existentes = forms.BooleanField(
        required=False,
        initial=True,
        label='Actualizar clientes existentes (mismo DNI o teléfono)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_archivo(self):
        f = self.cleaned_data['archivo']
        if not any(f.name.lower().endswith(e) for e in ('.csv', '.xlsx', '.xls')):
            raise ValidationError('Formato no soportado. Usá .csv, .xlsx o .xls.')
        if f.size > 10 * 1024 * 1024:
            raise ValidationError('El archivo no puede superar 10 MB.')
        return f
