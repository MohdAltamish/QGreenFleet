"""Generate clean, publication-grade architectural and data trust diagrams."""

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
charts_dir = _PROJECT_ROOT / "charts"
charts_dir.mkdir(parents=True, exist_ok=True)


def generate_architecture_diagram(out_path: Path) -> None:
    """Generate professional architecture diagram for Technical Report §8 and Streamlit home."""
    fig, ax = plt.subplots(figsize=(12, 6.8), dpi=200)
    ax.set_facecolor("#ffffff")
    fig.patch.set_facecolor("#ffffff")

    # Colors
    c_data = "#e8f4f8"
    b_data = "#2980b9"
    c_pred = "#eafaf1"
    b_pred = "#27ae60"
    c_opt = "#fef9e7"
    b_opt = "#f39c12"
    c_ui = "#f4ecf7"
    b_ui = "#8e44ad"

    # Box 1: Data Ingestion
    r1 = patches.FancyBboxPatch((0.5, 3.5), 2.8, 3.2, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor=c_data, edgecolor=b_data, lw=2)
    ax.add_patch(r1)
    ax.text(1.9, 6.3, "1. DATA ENGINE", fontsize=11, fontweight="bold", color=b_data, ha="center")
    ax.text(1.9, 5.7, "• 21,622 EU MRV Records\n• 13,820 Verified IMO Ships\n• Kaggle Voyage Profiles\n• Synthetic Fleets (S to XL)\n• Bunker Availability Maps", fontsize=9, color="#2c3e50", ha="center", va="top")

    # Box 2: Two-Stage Prediction
    r2 = patches.FancyBboxPatch((3.8, 3.5), 2.9, 3.2, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor=c_pred, edgecolor=b_pred, lw=2)
    ax.add_patch(r2)
    ax.text(5.25, 6.3, "2. TWO-STAGE SURROGATE", fontsize=11, fontweight="bold", color=b_pred, ha="center")
    ax.text(5.25, 5.7, "• Macro Stage (MRV Best)\n  Ship-Level XGBoost (R² 0.53)\n  Zero-Leakage IMO Partition\n• Micro Stage (Voyage Adjust)\n  Hydrodynamic Draft & Weather\n  Clipping: [0.7, 1.3]", fontsize=9, color="#2c3e50", ha="center", va="top")

    # Box 3: Quantum Optimization
    r3 = patches.FancyBboxPatch((7.2, 3.5), 3.0, 3.2, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor=c_opt, edgecolor=b_opt, lw=2)
    ax.add_patch(r3)
    ax.text(8.7, 6.3, "3. QUANTUM OPTIMIZER", fontsize=11, fontweight="bold", color=b_opt, ha="center")
    ax.text(8.7, 5.7, "• Discrete QIEA Superposition\n  Probabilistic Q-Bit Gates\n  Vessel Route & Fuel Mix\n• Continuous QPSO Dynamics\n  Cruising Speed Vectors\n• Non-Dominated Sorting\n  Pareto Elitist Archiving", fontsize=9, color="#2c3e50", ha="center", va="top")

    # Box 4: Decision Support & Delivery
    r4 = patches.FancyBboxPatch((10.7, 3.5), 2.8, 3.2, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor=c_ui, edgecolor=b_ui, lw=2)
    ax.add_patch(r4)
    ax.text(12.1, 6.3, "4. DECISION PLATFORM", fontsize=11, fontweight="bold", color=b_ui, ha="center")
    ax.text(12.1, 5.7, "• Streamlit Multi-Page UI\n• 13-Figure Plotly Library\n• Offline Case Study Loader\n• Dual PDF Export Center\n  Executive Summary (2-Page)\n  Technical Report (12-Page)", fontsize=9, color="#2c3e50", ha="center", va="top")

    # Bottom Banner: Constraint & Governance Foundation
    r_base = patches.FancyBboxPatch((0.5, 0.5), 13.0, 2.3, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor="#f8f9fa", edgecolor="#7f8c8d", lw=1.5, linestyle="--")
    ax.add_patch(r_base)
    ax.text(7.0, 2.4, "DOMAIN GOVERNANCE & MARITIME COMPLIANCE FOUNDATION", fontsize=10, fontweight="bold", color="#34495e", ha="center")
    ax.text(7.0, 1.8, "• C1 Demand Satisfaction: Greedy Fleet Capacity Repair    • C2/C6 Schedule Adherence: Arrival Windows & Speed Clipping [vmin, vmax]\n• C4 IMO CII Governance: Annual g-CO₂ / (DWT · nm) Benchmark Ratings    • C5 Alternative Fuel Bunkering: Port Infrastructure Verification\n• Life-Cycle Well-to-Wake (WtW) Emissions: IMO MEPC.376(80) Marine GHG Factors", fontsize=8.5, color="#555555", ha="center", va="top")

    # Arrows between blocks
    arrow_props = dict(arrowstyle="->", lw=2.5, color="#34495e")
    ax.annotate("", xy=(3.7, 5.1), xytext=(3.4, 5.1), arrowprops=arrow_props)
    ax.annotate("", xy=(7.1, 5.1), xytext=(6.8, 5.1), arrowprops=arrow_props)
    ax.annotate("", xy=(10.6, 5.1), xytext=(10.3, 5.1), arrowprops=arrow_props)

    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved architecture diagram to {out_path}")


def generate_data_trust_diagram(out_path: Path) -> None:
    """Generate data trust diagram for Technical Report §5."""
    fig, ax = plt.subplots(figsize=(11, 4.8), dpi=200)
    ax.set_facecolor("#ffffff")
    fig.patch.set_facecolor("#ffffff")

    c_step = "#fdfefe"
    b_step = "#16a085"

    steps = [
        ("1. Statutory Data Ingestion", "• 21,622 Annual Vessel Reports\n• EU MRV THETIS Verification\n• Statutory CO₂ & Fuel Returns\n• Cross-Checked vs AIS Tracks"),
        ("2. Anti-Leakage Partition", "• Grouped Strictly by IMO ID\n• Zero Ship Overlap (Train/Test)\n• Stratified by Naval Category\n• Prevents Memorization Bias"),
        ("3. Physics Conformance", "• Admiralty Law Verification\n  P ∝ v³ Resistance Scaling\n• Per-Category Imputations\n• Draft & Weather Bounding"),
        ("4. Operational Assurance", "• Out-of-Fold Cross Validation\n• Multi-Objective Fair Budgeting\n• Jargon Guard Executive Check\n• Production Reproducibility"),
    ]

    x_positions = [0.6, 3.4, 6.2, 9.0]
    for i, (title, desc) in enumerate(steps):
        x = x_positions[i]
        box = patches.FancyBboxPatch((x, 0.6), 2.4, 3.4, boxstyle="round,pad=0.2,rounding_size=0.15", facecolor="#e8f8f5", edgecolor=b_step, lw=2)
        ax.add_patch(box)
        ax.text(x + 1.2, 3.6, title, fontsize=9.5, fontweight="bold", color=b_step, ha="center")
        ax.text(x + 1.2, 3.1, desc, fontsize=8.2, color="#2c3e50", ha="center", va="top")

        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 2.75, 2.3), xytext=(x + 2.45, 2.3), arrowprops=dict(arrowstyle="->", lw=2, color=b_step))

    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4.5)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved data trust diagram to {out_path}")


if __name__ == "__main__":
    generate_architecture_diagram(charts_dir / "architecture_diagram.png")
    generate_data_trust_diagram(charts_dir / "data_trust_diagram.png")
