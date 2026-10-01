from __future__ import annotations
import streamlit as st
from sus_explorer.query_service import SUSExplorer


st.set_page_config(
    page_title="SUS Explorer — MVP",
    page_icon="💉",
    layout="wide",
)

st.title("SUS Explorer — MVP")

st.caption(
    "Gemini planeja → PyArrow consulta Parquet remoto → "
    "Gemini explica o agregado."
)

st.info(
    "Nenhum microdado individual é enviado ao LLM."
)


@st.cache_resource
def get_explorer():
    return SUSExplorer()


explorer = get_explorer()


q = st.text_input(
    "Pergunte sobre o SI-PNI",
    placeholder=(
        "Ex.: Quantas doses foram aplicadas "
        "em Canoas em maio de 2026?"
    ),
)


if q:
    try:
        with st.spinner("Interpretando a pergunta..."):
            x = explorer.ask(q)

        if x.get("needs_clarification"):
            st.warning(
                x.get("clarification_question")
                or "Preciso de mais informações."
            )

            missing = x.get("missing") or []

            if missing:
                if len(missing) == 1:
                    st.caption(
                        f"Informação faltante: {missing[0]}"
                    )
                else:
                    st.caption(
                        "Informações faltantes: "
                        + ", ".join(missing)
                    )

            with st.expander("Plano parcial do LLM"):
                st.json(
                    x.get("plan") or {}
                )

            st.stop()

        st.subheader("Resposta")

        st.write(
            x.get("answer", "")
        )

        result = x.get("result") or {}
        plan = x.get("plan") or {}

        provenance = (
            result.get("provenance", {})
            if isinstance(result, dict)
            else {}
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Operação",
                plan.get("operation", "—"),
            )

        with col2:
            st.metric(
                "Fragmentos",
                provenance.get(
                    "parquet_fragments",
                    "—",
                ),
            )

        with col3:
            elapsed = provenance.get(
                "elapsed_seconds"
            )

            st.metric(
                "Tempo backend",
                (
                    f"{elapsed:.2f}s"
                    if isinstance(
                        elapsed,
                        (int, float),
                    )
                    else "—"
                ),
            )

        with st.expander("Plano do LLM"):
            st.json(plan)

        with st.expander(
            "Resultado determinístico"
        ):
            st.json(
                result.get("data", {})
            )

        with st.expander("Proveniência"):
            st.json(provenance)

        warnings = result.get(
            "warnings",
            [],
        )

        for warning in warnings:
            st.warning(warning)

    except Exception as exc:
        st.error(
            "Não foi possível executar a consulta."
        )

        with st.expander("Detalhes técnicos"):
            st.exception(exc)
