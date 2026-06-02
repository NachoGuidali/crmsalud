import csv
import io

from django import forms
from django.core.exceptions import ValidationError

from .models import Lead, Plan, CampoPersonalizado


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'nombre_completo', 'dni', 'fecha_nacimiento', 'telefono', 'email',
            'localidad', 'provincia', 'plan_interes', 'grupo_familiar',
            'origen', 'agente', 'estado', 'prioridad', 'notas',
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

        # Agents can't reassign themselves
        if user and not user.can_see_all_leads:
            self.fields.pop('agente', None)
            self.fields.pop('estado', None) if 'estado' in self.fields else None

        self.fields['plan_interes'].queryset = Plan.objects.filter(activo=True)
        from apps.users.models import User as UserModel
        self.fields['agente'].queryset = UserModel.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')
        self.fields['telefono'].widget.attrs['placeholder'] = '+549XXXXXXXXXX'
        if not self.instance.pk:
            self.fields['telefono'].initial = '+549'

    def clean_dni(self):
        dni = self.cleaned_data.get('dni', '').strip()
        if not dni or dni == '0000000':
            return dni
        qs = Lead.objects.filter(dni=dni)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            dup = qs.first()
            raise ValidationError(f'Ya existe un lead con DNI {dni}: {dup.nombre_completo}.')
        from apps.clientes.models import Cliente
        dup_c = Cliente.objects.filter(dni=dni).first()
        if dup_c:
            raise ValidationError(f'Ya existe un cliente con DNI {dni}: {dup_c.nombre_completo}. Buscalo en Clientes.')
        return dni

    def clean_telefono(self):
        from utils.phone import normalize_ar_phone
        telefono = normalize_ar_phone(self.cleaned_data.get('telefono', '').strip())
        if not telefono:
            return telefono
        qs = Lead.objects.filter(telefono=telefono)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            dup = qs.first()
            raise ValidationError(f'Ya existe un lead con ese teléfono: {dup.nombre_completo}.')
        from apps.clientes.models import Cliente
        dup_c = Cliente.objects.filter(telefono=telefono).first()
        if dup_c:
            raise ValidationError(f'Ya existe un cliente con ese teléfono: {dup_c.nombre_completo}. Buscalo en Clientes.')
        return telefono


class LeadFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Buscar', widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre, DNI o teléfono'}))
    estado = forms.ChoiceField(required=False, choices=[('', 'Todos los estados')] + Lead.ESTADO_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    plan = forms.ModelChoiceField(queryset=Plan.objects.filter(activo=True), required=False, empty_label='Todos los planes', widget=forms.Select(attrs={'class': 'form-select'}))
    provincia = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Provincia'}))
    origen = forms.ChoiceField(required=False, choices=[('', 'Todos los orígenes')] + Lead.ORIGEN_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    prioridad = forms.ChoiceField(required=False, choices=[('', 'Todas las prioridades')] + Lead.PRIORIDAD_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    fecha_desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    fecha_hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    agente = forms.IntegerField(required=False, widget=forms.HiddenInput())


IMPORT_ACCEPTED_EXTENSIONS = ('.csv', '.xlsx', '.xls')


class LeadImportForm(forms.Form):
    archivo = forms.FileField(
        label='Archivo de contactos',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv,.xlsx,.xls'}),
        help_text='CSV o Excel (.xlsx). Columnas requeridas: nombre_completo (o name) y telefono.',
    )
    actualizar_existentes = forms.BooleanField(
        required=False,
        initial=True,
        label='Actualizar contactos existentes (mismo teléfono)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    asignar_agente = forms.BooleanField(
        required=False,
        initial=False,
        label='Asignarme como agente en los leads nuevos',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def clean_archivo(self):
        f = self.cleaned_data['archivo']
        ext = f.name.lower()
        if not any(ext.endswith(e) for e in IMPORT_ACCEPTED_EXTENSIONS):
            raise ValidationError('Formato no soportado. Usá .csv, .xlsx o .xls.')
        max_mb = 10
        if f.size > max_mb * 1024 * 1024:
            raise ValidationError(f'El archivo no puede superar {max_mb} MB.')
        return f


# Keep old name as alias for any existing references
LeadCSVImportForm = LeadImportForm


class EstadoChangeForm(forms.Form):
    estado = forms.ChoiceField(choices=Lead.ESTADO_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    nota = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Nota opcional sobre el cambio de estado'}))
    motivo_perdida = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Motivo por el que el lead no avanzó (obligatorio)'}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('estado') == Lead.ESTADO_PERDIDO and not cleaned.get('motivo_perdida', '').strip():
            self.add_error('motivo_perdida', 'Indicá el motivo de pérdida antes de continuar.')
        return cleaned


class CampoPersonalizadoForm(forms.ModelForm):
    opciones_texto = forms.CharField(
        required=False,
        label='Opciones (una por línea)',
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'placeholder': 'Opción 1\nOpción 2\nOpción 3'}),
        help_text='Solo para tipo "Lista de opciones".',
    )

    class Meta:
        model = CampoPersonalizado
        fields = ['nombre', 'tipo', 'alcance', 'requerido', 'orden', 'activo']
        widgets = {
            'nombre':   forms.TextInput(attrs={'class': 'form-control'}),
            'tipo':     forms.Select(attrs={'class': 'form-select'}),
            'alcance':  forms.Select(attrs={'class': 'form-select'}),
            'requerido': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'orden':    forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'activo':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.opciones:
            self.fields['opciones_texto'].initial = '\n'.join(self.instance.opciones)

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get('opciones_texto', '')
        instance.opciones = [o.strip() for o in raw.splitlines() if o.strip()]
        if commit:
            instance.save()
        return instance
