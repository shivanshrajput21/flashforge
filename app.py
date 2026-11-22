from collections import defaultdict
from pathlib import Path
import random
import streamlit as st

from exporter import export_anki, export_csv, list_decks, load_deck, log_metrics, save_deck
from generator import generate_cards
from models import Difficulty, Flashcard, RevisionStatus, RunMetrics
from utils import extract_text

DEFAULT_PROMPT_VERSION = "v2"


def get_available_prompt_versions() -> list[str]:
    """Return available prompt version names from prompts/ folder."""
    prompts_dir = Path("prompts")
    if not prompts_dir.is_dir():
        return ["v1"]
    versions = sorted([p.stem for p in prompts_dir.glob("v*.txt") if p.is_file()])
    return versions if versions else ["v1"]


def group_cards_by_topic(cards: list[Flashcard]) -> dict[str, list[tuple[int, Flashcard]]]:
    """Group flashcards by topic while preserving their original index in the main list."""
    grouped: dict[str, list[tuple[int, Flashcard]]] = defaultdict(list)
    for idx, card in enumerate(cards):
        grouped[card.topic].append((idx, card))
    return dict(grouped)


def init_session_state():
    """Initialize necessary Streamlit session state keys."""
    if "cards" not in st.session_state:
        st.session_state.cards = []
    if "last_metrics" not in st.session_state:
        st.session_state.last_metrics = None
    if "deck_name" not in st.session_state:
        st.session_state.deck_name = "My Flashcards"
    if "active_mode" not in st.session_state:
        st.session_state.active_mode = "Review & Edit"
    # Revision mode tracking
    if "revision_order" not in st.session_state:
        st.session_state.revision_order = []
    if "revision_index" not in st.session_state:
        st.session_state.revision_index = 0
    if "revision_flipped" not in st.session_state:
        st.session_state.revision_flipped = False


def start_revision_session(indices: list[int] | None = None):
    """Start or restart a revision study session."""
    if indices is None:
        order = list(range(len(st.session_state.cards)))
    else:
        order = list(indices)
    random.shuffle(order)
    st.session_state.revision_order = order
    st.session_state.revision_index = 0
    st.session_state.revision_flipped = False


def render_sidebar():
    """Render the sidebar for configuration, deck persistence, and export."""
    st.sidebar.title("⚡ FlashForge")

    # Prompt Version Selector
    st.sidebar.subheader("Configuration")
    versions = get_available_prompt_versions()
    default_idx = (
        versions.index(DEFAULT_PROMPT_VERSION)
        if DEFAULT_PROMPT_VERSION in versions
        else 0
    )
    prompt_version = st.sidebar.selectbox(
        "Prompt Version",
        options=versions,
        index=default_idx,
        help="Select which prompt template to use for generation.",
    )

    st.sidebar.divider()

    # Save & Load Decks
    st.sidebar.subheader("Deck Management")
    deck_name_input = st.sidebar.text_input(
        "Deck Name",
        value=st.session_state.deck_name,
    )
    if st.sidebar.button("💾 Save Current Deck", disabled=len(st.session_state.cards) == 0):
        try:
            path = save_deck(deck_name_input, st.session_state.cards, prompt_version=prompt_version)
            st.session_state.deck_name = deck_name_input
            st.sidebar.success(f"Saved to {path.name}")
        except Exception as e:
            st.sidebar.error(f"Error saving deck: {e}")

    # Load Existing Deck
    saved_decks = list_decks()
    if saved_decks:
        selected_deck = st.sidebar.selectbox("Load Saved Deck", options=["-- Select --"] + saved_decks)
        if st.sidebar.button("📂 Load Deck") and selected_deck != "-- Select --":
            try:
                loaded = load_deck(selected_deck)
                st.session_state.cards = loaded.cards
                st.session_state.deck_name = loaded.name
                st.session_state.last_metrics = None
                st.sidebar.success(f"Loaded '{loaded.name}' ({len(loaded.cards)} cards)")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error loading deck: {e}")

    st.sidebar.divider()

    # Export Buttons
    st.sidebar.subheader("Export")
    if st.session_state.cards:
        csv_data = export_csv(st.session_state.cards)
        anki_data = export_anki(st.session_state.cards)

        st.sidebar.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"{st.session_state.deck_name}.csv",
            mime="text/csv",
        )
        st.sidebar.download_button(
            label="📥 Download for Anki (.txt)",
            data=anki_data,
            file_name=f"{st.session_state.deck_name}_anki.txt",
            mime="text/plain",
        )
    else:
        st.sidebar.info("Generate or load cards to enable export.")

    return prompt_version


def render_input_panel(prompt_version: str):
    """Render the study notes input panel with text/file upload tabs."""
    st.header("1. Input Study Notes")

    tab_text, tab_txt, tab_pdf = st.tabs(["📝 Pasted Text", "📄 .txt Upload", "📕 .pdf Upload"])

    source_text = ""
    source_filename = None

    with tab_text:
        pasted = st.text_area(
            "Paste your notes or lecture summary here:",
            height=180,
            placeholder="Type or paste study text...",
        )
        if pasted.strip():
            source_text = pasted

    with tab_txt:
        uploaded_txt = st.file_uploader("Upload a text file", type=["txt"])
        if uploaded_txt is not None:
            source_text = uploaded_txt
            source_filename = uploaded_txt.name

    with tab_pdf:
        uploaded_pdf = st.file_uploader("Upload a PDF document", type=["pdf"])
        if uploaded_pdf is not None:
            source_text = uploaded_pdf
            source_filename = uploaded_pdf.name

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        generate_clicked = st.button("✨ Generate Flashcards", type="primary")

    if generate_clicked:
        if not source_text:
            st.warning("Please paste text or upload a .txt / .pdf file before generating.")
            return

        with st.spinner("Extracting text, chunking, and calling Gemini..."):
            try:
                raw_text = extract_text(source_text, filename=source_filename)
                if not raw_text.strip():
                    st.warning("The input document appears to be empty.")
                    return

                cards, metrics = generate_cards(raw_text, prompt_version=prompt_version)
                st.session_state.cards = cards
                st.session_state.last_metrics = metrics
                log_metrics(metrics)

                if metrics.api_failures > 0:
                    st.warning(f"Note: {metrics.api_failures} chunk(s) encountered server errors and were skipped.")

                st.success(f"Generated {len(cards)} flashcards!")
                st.rerun()
            except Exception as e:
                st.error(f"Generation failed: {e}")


def render_metrics_summary():
    """Display metrics for the most recent run."""
    m: RunMetrics = st.session_state.last_metrics
    if not m:
        return

    st.subheader("Run Summary")
    cols = st.columns(6)
    cols[0].metric("Chunks", m.chunks)
    cols[1].metric("First-try Fails", m.first_try_failures)
    cols[2].metric("Retries Used", m.retries)
    cols[3].metric("API Failures", m.api_failures)
    cols[4].metric("Cards Kept", m.cards_kept)
    cols[5].metric("Cards Dropped", m.cards_dropped)


def render_review_mode():
    """Render interactive cards grouped by topic with click-to-flip, editing, and deletion."""
    cards: list[Flashcard] = st.session_state.cards
    if not cards:
        st.info("No flashcards available. Paste notes above or load a saved deck.")
        return

    st.header(f"Cards ({len(cards)})")
    grouped = group_cards_by_topic(cards)

    # Track indices to delete after iteration
    index_to_delete = None

    for topic, topic_cards in grouped.items():
        with st.expander(f"📚 {topic} ({len(topic_cards)} cards)", expanded=True):
            for orig_idx, card in topic_cards:
                st.markdown(f"**Card #{orig_idx + 1}** — *Difficulty: `{card.difficulty.value}`*")

                col_card, col_actions = st.columns([4, 1])

                with col_card:
                    # Flip Card UI
                    flip_key = f"flip_{orig_idx}"
                    if flip_key not in st.session_state:
                        st.session_state[flip_key] = False

                    st.info(f"**Q:** {card.question}")
                    if st.session_state[flip_key]:
                        st.success(f"**A:** {card.answer}")
                        if st.button("Hide Answer", key=f"hide_{orig_idx}"):
                            st.session_state[flip_key] = False
                            st.rerun()
                    else:
                        if st.button("Show Answer", key=f"show_{orig_idx}"):
                            st.session_state[flip_key] = True
                            st.rerun()

                with col_actions:
                    edit_expander = st.popover("✏️ Edit")
                    with edit_expander:
                        new_q = st.text_area("Question", value=card.question, key=f"eq_{orig_idx}")
                        new_a = st.text_area("Answer", value=card.answer, key=f"ea_{orig_idx}")
                        new_t = st.text_input("Topic", value=card.topic, key=f"et_{orig_idx}")
                        diff_options = ["easy", "medium", "hard"]
                        new_d = st.selectbox(
                            "Difficulty",
                            options=diff_options,
                            index=diff_options.index(card.difficulty.value),
                            key=f"ed_{orig_idx}",
                        )

                        if st.button("Save Changes", key=f"save_edit_{orig_idx}"):
                            try:
                                updated_card = Flashcard(
                                    question=new_q,
                                    answer=new_a,
                                    topic=new_t,
                                    difficulty=Difficulty(new_d),
                                    status=card.status,
                                )
                                st.session_state.cards[orig_idx] = updated_card
                                st.success("Updated!")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Invalid card: {err}")

                    if st.button("🗑️ Delete", key=f"del_{orig_idx}"):
                        index_to_delete = orig_idx

                st.divider()

    if index_to_delete is not None:
        del st.session_state.cards[index_to_delete]
        st.rerun()


def render_revision_mode():
    """Render revision practice mode: one card at a time with flip, Known, and Needs Review."""
    cards: list[Flashcard] = st.session_state.cards
    if not cards:
        st.info("No flashcards available to study.")
        return

    order = st.session_state.revision_order
    # If uninitialized or card count changed, initialize
    if not order or max(order) >= len(cards):
        start_revision_session()
        st.rerun()

    curr_idx = st.session_state.revision_index
    total = len(order)

    # Progress bar and status tally
    known_count = sum(1 for c in cards if c.status == RevisionStatus.known)
    needs_review_count = sum(1 for c in cards if c.status == RevisionStatus.needs_review)

    st.header("🎯 Revision Mode")
    progress_val = curr_idx / total if total > 0 else 1.0
    st.progress(progress_val)
    st.caption(
        f"Card {min(curr_idx + 1, total)} of {total} | "
        f"Known: {known_count} | Needs Review: {needs_review_count}"
    )

    # Session complete view
    if curr_idx >= total:
        st.success("🎉 You have completed this revision session!")
        st.write(f"- **Known Cards:** {known_count}")
        st.write(f"- **Needs Review:** {needs_review_count}")

        col_restart_all, col_restart_needs = st.columns(2)
        with col_restart_all:
            if st.button("🔄 Restart All Cards"):
                start_revision_session()
                st.rerun()
        with col_restart_needs:
            needs_indices = [
                i for i, c in enumerate(cards) if c.status == RevisionStatus.needs_review
            ]
            if st.button(
                f"⚠️ Review 'Needs Review' Cards Only ({len(needs_indices)})",
                disabled=len(needs_indices) == 0,
            ):
                start_revision_session(needs_indices)
                st.rerun()
        return

    # Active Card Display
    actual_card_idx = order[curr_idx]
    card = cards[actual_card_idx]

    st.markdown(f"### Topic: *{card.topic}* (`{card.difficulty.value}`)")

    card_container = st.container(border=True)
    with card_container:
        st.markdown(f"## {card.question}")
        if st.session_state.revision_flipped:
            st.markdown("---")
            st.markdown(f"#### {card.answer}")
        else:
            if st.button("🔄 Flip to Reveal Answer", type="secondary"):
                st.session_state.revision_flipped = True
                st.rerun()

    # Grading actions (revealed once flipped, or allowed anytime)
    col_known, col_needs = st.columns(2)
    with col_known:
        if st.button("✅ Known", type="primary", use_container_width=True):
            card.status = RevisionStatus.known
            st.session_state.revision_index += 1
            st.session_state.revision_flipped = False
            st.rerun()

    with col_needs:
        if st.button("⚠️ Needs Review", type="secondary", use_container_width=True):
            card.status = RevisionStatus.needs_review
            st.session_state.revision_index += 1
            st.session_state.revision_flipped = False
            st.rerun()


def main():
    st.set_page_config(page_title="FlashForge", page_icon="⚡", layout="wide")
    init_session_state()

    prompt_version = render_sidebar()

    st.title("⚡ FlashForge: AI Study Notes to Flashcards")
    st.write(
        "Convert study notes and textbooks into concise, active-recall flashcards using Gemini."
    )

    render_input_panel(prompt_version)

    if st.session_state.last_metrics:
        render_metrics_summary()

    if st.session_state.cards:
        st.divider()
        mode = st.radio(
            "Study View",
            options=["Review & Edit", "Revision Practice"],
            horizontal=True,
        )
        if mode == "Review & Edit":
            render_review_mode()
        else:
            render_revision_mode()


if __name__ == "__main__":
    main()
