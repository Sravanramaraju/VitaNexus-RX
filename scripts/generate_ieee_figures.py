import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

# Configure matplotlib for publication-quality rendering
plt.rcParams['font.sans-serif'] = 'Arial'
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 9
plt.rcParams['axes.edgecolor'] = '#4A5568'
plt.rcParams['axes.linewidth'] = 0.8

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# FIGURE 1: Workflow Overview
# -------------------------------------------------------------
def generate_fig1():
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=300)
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.6)

    # Stages
    stages = [
        ("1. Intake & Provenance", "Patient Context\nVerified Indication\nActive Medicines", "#EBF8FF", "#2B6CB0"),
        ("2. Safety Evaluation", "DDInter DDI Check\nDrugCentral Disease\nTri-State Logic", "#E6FFFA", "#2C7A7B"),
        ("3. Candidate Gating", "Major/High Excluded\nUnresolved Flagged\nEligible Retained", "#FEFCBF", "#B7791F"),
        ("4. Learned Risk & Profile", "Calibrated LightGBM\nBootstrap + Conformal\nHGNN Event Profile", "#EDF2F7", "#4A5568"),
        ("5. Alternative Ranking", "50/30/20 Policy\nDeterministic Order\nClinician Rationale", "#EBF8FF", "#2B6CB0")
    ]

    box_w = 1.62
    box_h = 2.4
    y_pos = 0.6

    for i, (title, content, bg_col, border_col) in enumerate(stages):
        x_pos = 0.3 + i * 1.95
        # Main box
        rect = patches.FancyBboxPatch(
            (x_pos, y_pos), box_w, box_h,
            boxstyle="round,pad=0.08,rounding_size=0.12",
            facecolor=bg_col, edgecolor=border_col, linewidth=1.5
        )
        ax.add_patch(rect)
        
        # Header banner
        header_rect = patches.FancyBboxPatch(
            (x_pos, y_pos + box_h - 0.55), box_w, 0.55,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            facecolor=border_col, edgecolor=border_col, linewidth=1.0
        )
        ax.add_patch(header_rect)
        
        ax.text(x_pos + box_w/2, y_pos + box_h - 0.28, title,
                ha='center', va='center', fontsize=8.5, fontweight='bold', color='white')
        
        ax.text(x_pos + box_w/2, y_pos + (box_h - 0.55)/2, content,
                ha='center', va='center', fontsize=8, color='#1A202C', linespacing=1.4)
        
        # Flow arrow to next stage
        if i < len(stages) - 1:
            ax.annotate('', xy=(x_pos + box_w + 0.33, y_pos + box_h/2),
                        xytext=(x_pos + box_w, y_pos + box_h/2),
                        arrowprops=dict(arrowstyle="-|>", color="#4A5568", lw=1.8, mutation_scale=12))

    plt.tight_layout()
    out_path = DOCS_DIR / "fig1_workflow.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated {out_path}")

# -------------------------------------------------------------
# FIGURE 2: System Architecture
# -------------------------------------------------------------
def generate_fig2():
    fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=300)
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)

    # Tier 1: Client UI
    ui_rect = patches.FancyBboxPatch((0.4, 1.4), 1.8, 2.2,
                                     boxstyle="round,pad=0.08,rounding_size=0.12",
                                     facecolor="#EBF8FF", edgecolor="#2B6CB0", linewidth=1.5)
    ax.add_patch(ui_rect)
    ax.text(1.3, 3.2, "Clinician UI\n(React 18 / Vite)", ha='center', va='center', fontsize=9, fontweight='bold', color="#1A365D")
    ax.text(1.3, 2.2, "• Consultation Intake\n• Safety Audit View\n• ADR Risk Display\n• HGNN Profile\n• Ranked Alternatives",
            ha='center', va='center', fontsize=7.5, color="#2D3748", linespacing=1.3)

    # Tier 2: Express 5 API Gateway
    api_rect = patches.FancyBboxPatch((3.0, 1.0), 2.2, 3.0,
                                      boxstyle="round,pad=0.08,rounding_size=0.12",
                                      facecolor="#F7FAFC", edgecolor="#2D3748", linewidth=1.5)
    ax.add_patch(api_rect)
    ax.text(4.1, 3.65, "Backend API Gateway\n(Express 5 / Node.js)", ha='center', va='center', fontsize=9, fontweight='bold', color="#1A202C")
    ax.text(4.1, 2.4, "• Route Guards & Sessions\n• Zod Schema Validation\n• Terminology Resolution\n• Tri-State Safety Gating\n• 50/30/20 Ranking Engine\n• Immutable Audit Hashes",
            ha='center', va='center', fontsize=7.5, color="#2D3748", linespacing=1.35)

    # Tier 3: Persistence
    db_rect = patches.FancyBboxPatch((3.0, 0.05), 2.2, 0.65,
                                     boxstyle="round,pad=0.06,rounding_size=0.08",
                                     facecolor="#FEFCBF", edgecolor="#B7791F", linewidth=1.2)
    ax.add_patch(db_rect)
    ax.text(4.1, 0.38, "PostgreSQL + Prisma ORM\n(Consultation & Audit Snapshots)", ha='center', va='center', fontsize=7.5, fontweight='bold', color="#744210")

    # Tier 4: Knowledge Bases
    kb1_rect = patches.FancyBboxPatch((6.0, 3.1), 1.7, 1.0,
                                      boxstyle="round,pad=0.06,rounding_size=0.08",
                                      facecolor="#E6FFFA", edgecolor="#2C7A7B", linewidth=1.2)
    ax.add_patch(kb1_rect)
    ax.text(6.85, 3.6, "DDInter 2.0\nKnowledge Base", ha='center', va='center', fontsize=8, fontweight='bold', color="#234E52")
    ax.text(6.85, 3.3, "Drug-Drug Interactions", ha='center', va='center', fontsize=7, color="#285E61")

    kb2_rect = patches.FancyBboxPatch((6.0, 1.9), 1.7, 1.0,
                                      boxstyle="round,pad=0.06,rounding_size=0.08",
                                      facecolor="#E6FFFA", edgecolor="#2C7A7B", linewidth=1.2)
    ax.add_patch(kb2_rect)
    ax.text(6.85, 2.4, "DrugCentral 2021\nKnowledge Base", ha='center', va='center', fontsize=8, fontweight='bold', color="#234E52")
    ax.text(6.85, 2.1, "Drug-Disease & Indications", ha='center', va='center', fontsize=7, color="#285E61")

    # Tier 5: Python ML Microservice
    ml_rect = patches.FancyBboxPatch((8.0, 0.6), 1.8, 3.5,
                                     boxstyle="round,pad=0.08,rounding_size=0.12",
                                     facecolor="#EDF2F7", edgecolor="#4A5568", linewidth=1.5)
    ax.add_patch(ml_rect)
    ax.text(8.9, 3.8, "ML Microservice\n(FastAPI :8000)", ha='center', va='center', fontsize=9, fontweight='bold', color="#1A202C")
    
    # Sub-boxes in ML
    lgb_rect = patches.FancyBboxPatch((8.15, 2.0), 1.5, 1.45,
                                      boxstyle="round,pad=0.04,rounding_size=0.06",
                                      facecolor="#FFFFFF", edgecolor="#3182CE", linewidth=1.2)
    ax.add_patch(lgb_rect)
    ax.text(8.9, 3.15, "Frozen LightGBM", ha='center', va='center', fontsize=8, fontweight='bold', color="#2B6CB0")
    ax.text(8.9, 2.55, "• 15,369 Features\n• Isotonic Calibrated\n• 20 Bootstrap Replicas\n• Split Conformal Set",
            ha='center', va='center', fontsize=6.8, color="#2D3748", linespacing=1.25)

    hgnn_rect = patches.FancyBboxPatch((8.15, 0.75), 1.5, 1.1,
                                       boxstyle="round,pad=0.04,rounding_size=0.06",
                                       facecolor="#FFFFFF", edgecolor="#805AD5", linewidth=1.2)
    ax.add_patch(hgnn_rect)
    ax.text(8.9, 1.55, "Completed HGNN", ha='center', va='center', fontsize=8, fontweight='bold', color="#553C9A")
    ax.text(8.9, 1.12, "• 4 Node / 10 Edge Hetero\n• SAGEConv (96h -> 100)\n• 100 MedDRA Event Labels",
            ha='center', va='center', fontsize=6.8, color="#2D3748", linespacing=1.25)

    # Connections
    # UI <-> API
    ax.annotate('', xy=(3.0, 2.5), xytext=(2.2, 2.5),
                arrowprops=dict(arrowstyle="<|-|>", color="#2B6CB0", lw=1.6))
    ax.text(2.6, 2.7, "HTTPS / REST", ha='center', va='bottom', fontsize=7, color="#2B6CB0")

    # API <-> DB
    ax.annotate('', xy=(4.1, 0.7), xytext=(4.1, 1.0),
                arrowprops=dict(arrowstyle="<|-|>", color="#B7791F", lw=1.4))

    # API <-> Knowledge Bases
    ax.annotate('', xy=(6.0, 3.6), xytext=(5.2, 3.2),
                arrowprops=dict(arrowstyle="<|-|>", color="#2C7A7B", lw=1.4))
    ax.annotate('', xy=(6.0, 2.4), xytext=(5.2, 2.4),
                arrowprops=dict(arrowstyle="<|-|>", color="#2C7A7B", lw=1.4))

    # API <-> ML Service
    ax.annotate('', xy=(8.0, 2.7), xytext=(5.2, 1.8),
                arrowprops=dict(arrowstyle="<|-|>", color="#4A5568", lw=1.6))
    ax.text(6.6, 1.55, "Internal RPC\nLoopback :8000", ha='center', va='center', fontsize=7, color="#4A5568")

    plt.tight_layout()
    out_path = DOCS_DIR / "fig2_architecture.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated {out_path}")

# -------------------------------------------------------------
# FIGURE 3: Terminology Bridge Pipeline
# -------------------------------------------------------------
def generate_fig3():
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=300)
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.8)

    # Input Box
    in_rect = patches.FancyBboxPatch((0.2, 2.0), 1.4, 1.2,
                                     boxstyle="round,pad=0.08,rounding_size=0.1",
                                     facecolor="#EBF8FF", edgecolor="#2B6CB0", linewidth=1.5)
    ax.add_patch(in_rect)
    ax.text(0.9, 2.75, "Source Term", ha='center', va='center', fontsize=8.5, fontweight='bold', color="#1A365D")
    ax.text(0.9, 2.3, "DDInter /\nDrugCentral /\nIndian Medicine", ha='center', va='center', fontsize=7.2, color="#2D3748")

    # Basic Normalization
    norm_rect = patches.FancyBboxPatch((1.9, 2.0), 1.3, 1.2,
                                       boxstyle="round,pad=0.08,rounding_size=0.1",
                                       facecolor="#F7FAFC", edgecolor="#4A5568", linewidth=1.2)
    ax.add_patch(norm_rect)
    ax.text(2.55, 2.75, "Canonical\nNormalization", ha='center', va='center', fontsize=8, fontweight='bold', color="#2D3748")
    ax.text(2.55, 2.25, "• NFKC Unicode\n• Uppercase / Trim\n• Strip Punctuation", ha='center', va='center', fontsize=6.8, color="#4A5568")

    # Connect In -> Norm
    ax.annotate('', xy=(1.9, 2.6), xytext=(1.6, 2.6),
                arrowprops=dict(arrowstyle="-|>", color="#4A5568", lw=1.5))

    # Big Bridge Container
    bridge_rect = patches.FancyBboxPatch((3.5, 0.4), 3.4, 4.0,
                                         boxstyle="round,pad=0.1,rounding_size=0.12",
                                         facecolor="#EDF2F7", edgecolor="#2C7A7B", linewidth=1.6)
    ax.add_patch(bridge_rect)
    ax.text(5.2, 4.15, "Vocabulary-Aware Terminology Bridge", ha='center', va='center', fontsize=9, fontweight='bold', color="#234E52")
    ax.text(5.2, 3.88, "(Top-Down 7-Level Resolution Hierarchy)", ha='center', va='center', fontsize=7.5, fontstyle='italic', color="#285E61")

    # 6 Levels inside Bridge
    levels = [
        ("L1. Exact Match", "Direct normalized string lookup in vocabulary"),
        ("L2. Clinical Aliases", "Project-defined canonical aliases (e.g. Paracetamol)"),
        ("L3. Orthographic Rules", "British <-> American rules (Gastroesophageal/Gastrooesophageal)"),
        ("L4. Token-Set Reorder", "Sorted token permutation (Atopic dermatitis <-> Dermatitis atopic)"),
        ("L5. Salt/Form Equivalence", "Strip/append salt suffixes (Metformin <-> Metformin HCl)"),
        ("L6. Curated Synonym Crosswalk", "Pharmacological synonym mapping (Aspirin <-> Acetylsalicylic acid)")
    ]

    for idx, (ltitle, ldesc) in enumerate(levels):
        ly = 3.35 - idx * 0.52
        lrect = patches.FancyBboxPatch((3.65, ly), 3.1, 0.42,
                                       boxstyle="round,pad=0.04,rounding_size=0.06",
                                       facecolor="#FFFFFF", edgecolor="#CBD5E0", linewidth=1.0)
        ax.add_patch(lrect)
        ax.text(3.75, ly + 0.28, ltitle, ha='left', va='center', fontsize=7.2, fontweight='bold', color="#2B6CB0")
        ax.text(3.75, ly + 0.12, ldesc, ha='left', va='center', fontsize=6.2, color="#4A5568")

    # Connect Norm -> Bridge
    ax.annotate('', xy=(3.5, 2.6), xytext=(3.2, 2.6),
                arrowprops=dict(arrowstyle="-|>", color="#4A5568", lw=1.5))

    # Frozen Vocabulary Box
    froz_rect = patches.FancyBboxPatch((7.2, 1.8), 1.2, 1.6,
                                       boxstyle="round,pad=0.06,rounding_size=0.1",
                                       facecolor="#FEFCBF", edgecolor="#B7791F", linewidth=1.5)
    ax.add_patch(froz_rect)
    ax.text(7.8, 3.05, "Validate Against\nFrozen FAERS\nVocabularies", ha='center', va='center', fontsize=7.5, fontweight='bold', color="#744210")
    ax.text(7.8, 2.25, "• 4,359 Candidates\n• 5,000 Indications\n• 1,001 Medicines\n(15,369 Features)",
            ha='center', va='center', fontsize=6.5, color="#744210", linespacing=1.2)

    # Connect Bridge -> Vocab
    ax.annotate('', xy=(7.2, 2.6), xytext=(6.9, 2.6),
                arrowprops=dict(arrowstyle="-|>", color="#4A5568", lw=1.5))

    # Outcomes
    # Resolved -> FeatureBuilder
    res_rect = patches.FancyBboxPatch((8.7, 2.8), 1.15, 1.1,
                                      boxstyle="round,pad=0.06,rounding_size=0.08",
                                      facecolor="#C6F6D5", edgecolor="#22543D", linewidth=1.4)
    ax.add_patch(res_rect)
    ax.text(9.27, 3.55, "RESOLVED", ha='center', va='center', fontsize=7.8, fontweight='bold', color="#22543D")
    ax.text(9.27, 3.1, "FeatureBuilder\n-> LightGBM\nScoring Allowed", ha='center', va='center', fontsize=6.8, color="#22543D")

    # Unresolved -> Fail Closed
    unres_rect = patches.FancyBboxPatch((8.7, 0.9), 1.15, 1.1,
                                        boxstyle="round,pad=0.06,rounding_size=0.08",
                                        facecolor="#FED7D7", edgecolor="#742A2A", linewidth=1.4)
    ax.add_patch(unres_rect)
    ax.text(9.27, 1.65, "UNRESOLVED /\nAMBIGUOUS", ha='center', va='center', fontsize=7.5, fontweight='bold', color="#742A2A")
    ax.text(9.27, 1.18, "L7 Fallback:\nOUT_OF_VOCAB\nNo Fabricated 0", ha='center', va='center', fontsize=6.8, color="#742A2A")

    # Branch arrows
    ax.annotate('', xy=(8.7, 3.35), xytext=(8.4, 2.8),
                arrowprops=dict(arrowstyle="-|>", color="#22543D", lw=1.6))
    ax.text(8.4, 3.25, "Unique Match", ha='center', va='center', fontsize=6.2, color="#22543D", fontweight='bold')

    ax.annotate('', xy=(8.7, 1.45), xytext=(8.4, 2.4),
                arrowprops=dict(arrowstyle="-|>", color="#742A2A", lw=1.6))
    ax.text(8.4, 1.8, "No / Multi Match", ha='center', va='center', fontsize=6.2, color="#742A2A", fontweight='bold')

    plt.tight_layout()
    out_path = DOCS_DIR / "fig3_bridge.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated {out_path}")

# -------------------------------------------------------------
# FIGURE 4: Safety Gate Decision Flowchart
# -------------------------------------------------------------
def generate_fig4():
    fig, ax = plt.subplots(figsize=(7.2, 3.0), dpi=300)
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.8)

    # Candidate In
    c_rect = patches.FancyBboxPatch((0.2, 1.8), 1.3, 1.0,
                                    boxstyle="round,pad=0.08,rounding_size=0.1",
                                    facecolor="#EBF8FF", edgecolor="#2B6CB0", linewidth=1.4)
    ax.add_patch(c_rect)
    ax.text(0.85, 2.45, "Candidate\nAlternative", ha='center', va='center', fontsize=8, fontweight='bold', color="#1A365D")
    ax.text(0.85, 2.05, "From DrugCentral\nSame Indication", ha='center', va='center', fontsize=6.8, color="#2D3748")

    # Gate 1: DDI Check
    ddi_rect = patches.FancyBboxPatch((1.9, 1.7), 1.8, 1.2,
                                      boxstyle="round,pad=0.08,rounding_size=0.1",
                                      facecolor="#F7FAFC", edgecolor="#2D3748", linewidth=1.4)
    ax.add_patch(ddi_rect)
    ax.text(2.8, 2.55, "Gate 1: DDInter DDI", ha='center', va='center', fontsize=8, fontweight='bold', color="#1A202C")
    ax.text(2.8, 2.05, "• Major -> NOT_RECOMMENDED\n• Unresolved -> CLINICAL_REVIEW\n• Minor / Moderate / Empty -> Pass",
            ha='center', va='center', fontsize=6.5, color="#2D3748")

    # Gate 2: Drug-Disease Check
    dis_rect = patches.FancyBboxPatch((4.1, 1.7), 1.8, 1.2,
                                      boxstyle="round,pad=0.08,rounding_size=0.1",
                                      facecolor="#F7FAFC", edgecolor="#2D3748", linewidth=1.4)
    ax.add_patch(dis_rect)
    ax.text(5.0, 2.55, "Gate 2: Drug-Disease", ha='center', va='center', fontsize=8, fontweight='bold', color="#1A202C")
    ax.text(5.0, 2.05, "• High -> NOT_RECOMMENDED\n• Incomplete -> CLINICAL_REVIEW\n• Low / Mod / None -> Pass",
            ha='center', va='center', fontsize=6.5, color="#2D3748")

    # ML Scoring
    ml_rect = patches.FancyBboxPatch((6.3, 1.7), 1.6, 1.2,
                                     boxstyle="round,pad=0.08,rounding_size=0.1",
                                     facecolor="#E6FFFA", edgecolor="#2C7A7B", linewidth=1.4)
    ax.add_patch(ml_rect)
    ax.text(7.1, 2.55, "ML Adverse Risk", ha='center', va='center', fontsize=8, fontweight='bold', color="#234E52")
    ax.text(7.1, 2.05, "• LightGBM serious-outcome\n• Isotonic probability\n• Upper bootstrap bound\n• Conformal set context",
            ha='center', va='center', fontsize=6.5, color="#285E61")

    # Ranking
    rank_rect = patches.FancyBboxPatch((8.3, 1.6), 1.5, 1.4,
                                       boxstyle="round,pad=0.08,rounding_size=0.12",
                                       facecolor="#C6F6D5", edgecolor="#22543D", linewidth=1.5)
    ax.add_patch(rank_rect)
    ax.text(9.05, 2.65, "Composite Ranking", ha='center', va='center', fontsize=8, fontweight='bold', color="#22543D")
    ax.text(9.05, 2.05, "0.50 * AdjLGBMRisk\n+ 0.30 * DdiRisk\n+ 0.20 * DiseaseRisk\n\n(Deterministic Sort)",
            ha='center', va='center', fontsize=6.5, color="#22543D", linespacing=1.2)

    # Exclusions
    notrec_rect = patches.FancyBboxPatch((2.2, 0.2), 1.8, 0.75,
                                         boxstyle="round,pad=0.06,rounding_size=0.08",
                                         facecolor="#FED7D7", edgecolor="#742A2A", linewidth=1.3)
    ax.add_patch(notrec_rect)
    ax.text(3.1, 0.58, "NOT RECOMMENDED", ha='center', va='center', fontsize=7.5, fontweight='bold', color="#742A2A")
    ax.text(3.1, 0.35, "Excluded before ML scoring", ha='center', va='center', fontsize=6.5, color="#742A2A")

    review_rect = patches.FancyBboxPatch((4.5, 0.2), 2.0, 0.75,
                                         boxstyle="round,pad=0.06,rounding_size=0.08",
                                         facecolor="#FEFCBF", edgecolor="#B7791F", linewidth=1.3)
    ax.add_patch(review_rect)
    ax.text(5.5, 0.58, "REQUIRES CLINICAL REVIEW", ha='center', va='center', fontsize=7.5, fontweight='bold', color="#744210")
    ax.text(5.5, 0.35, "Incomplete / failed source lookup", ha='center', va='center', fontsize=6.5, color="#744210")

    # Arrows
    ax.annotate('', xy=(1.9, 2.3), xytext=(1.5, 2.3), arrowprops=dict(arrowstyle="-|>", color="#4A5568", lw=1.5))
    ax.annotate('', xy=(4.1, 2.3), xytext=(3.7, 2.3), arrowprops=dict(arrowstyle="-|>", color="#22543D", lw=1.5))
    ax.annotate('', xy=(6.3, 2.3), xytext=(5.9, 2.3), arrowprops=dict(arrowstyle="-|>", color="#22543D", lw=1.5))
    ax.annotate('', xy=(8.3, 2.3), xytext=(7.9, 2.3), arrowprops=dict(arrowstyle="-|>", color="#22543D", lw=1.5))

    # Reject arrows down
    ax.annotate('', xy=(2.8, 0.95), xytext=(2.8, 1.7), arrowprops=dict(arrowstyle="-|>", color="#742A2A", lw=1.3, linestyle="--"))
    ax.text(2.6, 1.25, "Major", ha='right', va='center', fontsize=6.5, color="#742A2A")

    ax.annotate('', xy=(3.4, 0.95), xytext=(4.7, 1.7), arrowprops=dict(arrowstyle="-|>", color="#742A2A", lw=1.3, linestyle="--"))
    ax.text(4.2, 1.15, "High Restr.", ha='center', va='center', fontsize=6.5, color="#742A2A")

    ax.annotate('', xy=(5.2, 0.95), xytext=(3.5, 1.7), arrowprops=dict(arrowstyle="-|>", color="#B7791F", lw=1.3, linestyle="--"))
    ax.annotate('', xy=(5.5, 0.95), xytext=(5.2, 1.7), arrowprops=dict(arrowstyle="-|>", color="#B7791F", lw=1.3, linestyle="--"))
    ax.text(5.7, 1.35, "Unresolved Term", ha='left', va='center', fontsize=6.5, color="#744210")

    plt.tight_layout()
    out_path = DOCS_DIR / "fig4_safety_gate.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated {out_path}")

# -------------------------------------------------------------
# FIGURE 5: Temporal Data Partitioning Timeline
# -------------------------------------------------------------
def generate_fig5():
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=300)
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.6)

    ax.text(0.2, 3.2, "Chronological FAERS Data Partitions (18 Quarters: 2022Q1 - 2026Q2)",
            ha='left', va='center', fontsize=9, fontweight='bold', color="#1A365D")

    # LightGBM Bar
    ax.text(0.2, 2.4, "LightGBM Pipeline (4.91M Training Reports):", ha='left', va='center', fontsize=8, fontweight='bold', color="#2D3748")
    
    # 2022Q1 - 2025Q2 (Train)
    rect1 = patches.Rectangle((0.2, 1.7), 5.6, 0.5, facecolor="#2B6CB0", edgecolor="#1A365D", linewidth=1.0)
    ax.add_patch(rect1)
    ax.text(3.0, 1.95, "Model Training: 2022Q1 - 2025Q2 (4,910,268 Reports)", ha='center', va='center', fontsize=7.5, color="white", fontweight='bold')

    # 2025Q3 (Isotonic)
    rect2 = patches.Rectangle((5.8, 1.7), 1.0, 0.5, facecolor="#4299E1", edgecolor="#2B6CB0", linewidth=1.0)
    ax.add_patch(rect2)
    ax.text(6.3, 1.95, "Iso Calib\n2025Q3", ha='center', va='center', fontsize=6.5, color="white", fontweight='bold')

    # 2025Q4 (Conformal)
    rect3 = patches.Rectangle((6.8, 1.7), 1.1, 0.5, facecolor="#63B3ED", edgecolor="#3182CE", linewidth=1.0)
    ax.add_patch(rect3)
    ax.text(7.35, 1.95, "Conf Calib\n2025Q4", ha='center', va='center', fontsize=6.5, color="#1A202C", fontweight='bold')

    # 2026Q1-Q2 (Holdout)
    rect4 = patches.Rectangle((7.9, 1.7), 1.9, 0.5, facecolor="#48BB78", edgecolor="#22543D", linewidth=1.0)
    ax.add_patch(rect4)
    ax.text(8.85, 1.95, "Untouched Holdout\n2026Q1-Q2 (696K)", ha='center', va='center', fontsize=6.8, color="white", fontweight='bold')

    # HGNN Bar
    ax.text(0.2, 1.1, "Supplementary HGNN Event Profile (100 MedDRA Reaction Labels):", ha='left', va='center', fontsize=8, fontweight='bold', color="#2D3748")

    # 2022Q1 - 2025Q4 (HGNN Train)
    hgnn_t = patches.Rectangle((0.2, 0.4), 7.7, 0.5, facecolor="#805AD5", edgecolor="#553C9A", linewidth=1.0)
    ax.add_patch(hgnn_t)
    ax.text(4.05, 0.65, "Completed Selection & Final Refit Training: 2022Q1 - 2025Q4 (16 Quarters)", ha='center', va='center', fontsize=7.5, color="white", fontweight='bold')

    # 2026Q1-Q2 (HGNN Test)
    hgnn_test = patches.Rectangle((7.9, 0.4), 1.9, 0.5, facecolor="#38B2AC", edgecolor="#234E52", linewidth=1.0)
    ax.add_patch(hgnn_test)
    ax.text(8.85, 0.65, "Temporal Test\n2026Q1-Q2", ha='center', va='center', fontsize=6.8, color="white", fontweight='bold')

    plt.tight_layout()
    out_path = DOCS_DIR / "fig5_timeline.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated {out_path}")

if __name__ == "__main__":
    generate_fig1()
    generate_fig2()
    generate_fig3()
    generate_fig4()
    generate_fig5()
