import io
import logging

from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_cotizacion_pdf(cotizacion) -> bytes:
    """Render the cotizacion as a PDF using WeasyPrint."""
    try:
        from weasyprint import HTML, CSS
        html_string = render_to_string('quotes/cotizacion_pdf.html', {'cotizacion': cotizacion, 'integrantes': cotizacion.integrantes.all()})
        pdf_bytes = HTML(string=html_string, base_url=settings.STATIC_ROOT).write_pdf()
        return pdf_bytes
    except ImportError:
        logger.warning('WeasyPrint not installed. Returning empty PDF bytes.')
        return b''
    except Exception as e:
        logger.exception('Error generating PDF for cotizacion %s: %s', cotizacion.pk, e)
        raise
