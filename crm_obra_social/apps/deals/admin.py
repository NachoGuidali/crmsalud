from django.contrib import admin
from .models import Pipeline, PipelineStage, Deal, DealHistory


class StageInline(admin.TabularInline):
    model = PipelineStage
    extra = 1
    fields = ('nombre', 'orden', 'color')


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    inlines = [StageInline]


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'pipeline', 'stage', 'valor', 'agente', 'created_at')
    list_filter = ('pipeline', 'stage', 'agente')
    raw_id_fields = ('lead',)
