"""Shared presentation palette and accessible provenance components.

These labels never mutate analytical classifications or infer enrichment.
"""
from html import escape
import pandas as pd
import streamlit as st

PROVENANCE_STYLES = {
    'DIRECT': {'color': '#16A34A', 'label': 'Observado', 'text': '#000000'},
    'DERIVED': {'color': '#9333EA', 'label': 'Calculado', 'text': '#FFFFFF'},
    'ENRICHED': {'color': '#2563EB', 'label': 'Contextualizado', 'text': '#FFFFFF'},
}
NEUTRAL_REFERENCE = '#808080'


def provenance_label(classification):
    style = PROVENANCE_STYLES.get(classification)
    return f"{classification} — {style['label']}" if style else 'Proveniência não classificada'


def badge_html(classification):
    style = PROVENANCE_STYLES[classification]
    return (f'<span style="display:inline-block;padding:0.15rem 0.5rem;margin:0.2rem 0.5rem 0.2rem 0;'
            f'border:1px solid {style["color"]};border-left:5px solid {style["color"]};'
            'border-radius:0.35rem;color:inherit;background:transparent;">'
            f'{escape(provenance_label(classification))}</span>')


def render_provenance_legend():
    st.markdown('<div aria-label="Legenda de proveniência">' +
                ''.join(badge_html(kind) for kind in PROVENANCE_STYLES) + '</div>',
                unsafe_allow_html=True)
    st.caption('Legenda: fonte observada · métrica calculada · contexto de fonte externa documentada. A legenda não indica que todas as categorias estão presentes neste resultado.')


def install_provenance_styles():
    # Keyed Streamlit containers avoid global overrides of app/theme foregrounds.
    rules = []
    for kind, style in PROVENANCE_STYLES.items():
        rules.append(f'[class*="st-key-sus_prov_{kind}_"] {{'
                     f'border-left:4px solid {style["color"]};padding-left:0.75rem;}}')
    st.markdown('<style>' + ''.join(rules) + '</style>', unsafe_allow_html=True)


def provenance_heading(title, classification, key):
    with st.container(key=f'sus_prov_{classification}_{key}'):
        st.subheader(f'{title} · {provenance_label(classification)}')


def provenance_metric(container, label, value, classification, key):
    with container.container(key=f'sus_prov_{classification}_{key}'):
        st.metric(f'{label} · {provenance_label(classification)}', value)


def documented_enrichment(row):
    """Existing terminology contract: a definition with its external source."""
    return (isinstance(row.get('definition'), str) and bool(row['definition'].strip())
            and isinstance(row.get('definition_source'), str) and bool(row['definition_source'].strip())
            and not row.get('conflict', False))


def style_provenance_table(table, column_classes=None, enriched_cells=None):
    """Style exact text cells only; table data and exports remain unchanged."""
    classes = column_classes or {}
    enriched = enriched_cells or set()
    def styles(frame):
        css = pd.DataFrame('', index=frame.index, columns=frame.columns)
        for column in frame.columns:
            kind = classes.get(column)
            for index in frame.index:
                selected = 'ENRICHED' if (index, column) in enriched else kind
                if selected in PROVENANCE_STYLES:
                    style = PROVENANCE_STYLES[selected]
                    css.loc[index, column] = (f'background-color: {style["color"]};'
                                               f'color: {style["text"]};font-weight: 600;')
        return css
    return table.style.apply(styles, axis=None)
