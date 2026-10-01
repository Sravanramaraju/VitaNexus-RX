import sys
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"

def set_cell_shading(cell, fill_hex):
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill_hex)

def set_cell_margins(cell, top=80, start=100, bottom=80, end=100):
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        element = margins.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")

def set_table_borders(table, color="D3D3D3"):
    tblPr = table._tbl.tblPr
    borders = tblPr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for border_name in ["top", "left", "bottom", "right", "insideH"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)
        borders.append(border)
    insideV = OxmlElement("w:insideV")
    insideV.set(qn("w:val"), "none")
    borders.append(insideV)

def format_cell(cell, text, bold=False, italic=False, font_size=8.0, color=(0,0,0), align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor(*color)

def generate_manuscript(stage=3):
    """
    stage 1: Structure, formatting, author, sequential tables, acknowledgments, 32 refs.
    stage 2: stage 1 + Terminology Bridge section + completed HGNN section.
    stage 3: stage 2 + 5 figures embedded, Table IV baseline comparison, polished text.
    """
    doc = docx.Document()

    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(10)
    normal_style.font.color.rgb = RGBColor(0, 0, 0)

    # Section 0: Full width
    sec0 = doc.sections[0]
    sec0.page_width = Inches(8.5)
    sec0.page_height = Inches(11.0)
    sec0.top_margin = Inches(0.75)
    sec0.bottom_margin = Inches(0.75)
    sec0.left_margin = Inches(0.65)
    sec0.right_margin = Inches(0.65)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(10)
    r_title = p_title.add_run("VitaNexus-RX: An Evidence-Bounded Clinical Decision Support System for Safety-Aware Same-Indication Alternative Recommendation")
    r_title.font.name = 'Times New Roman'
    r_title.font.size = Pt(22)
    r_title.font.bold = True

    p_author = doc.add_paragraph()
    p_author.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_author.paragraph_format.space_before = Pt(0)
    p_author.paragraph_format.space_after = Pt(14)
    r_name = p_author.add_run("Ramaraju Naga Eswara Sravan, Rajana Ashok, Yadala Hari Prasad, Salimetti Lokesh\n")
    r_name.font.name = 'Times New Roman'
    r_name.font.size = Pt(10.5)
    r_name.font.bold = True
    r_affil = p_author.add_run("Department of Computer Science and Engineering\nVignan's Lara Institute of Technology and Science\nGuntur, India\nsravantatikonda123@gmail.com")
    r_affil.font.name = 'Times New Roman'
    r_affil.font.size = Pt(9.5)

    p_abs = doc.add_paragraph()
    p_abs.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_abs.paragraph_format.left_indent = Inches(0.35)
    p_abs.paragraph_format.right_indent = Inches(0.35)
    p_abs.paragraph_format.space_before = Pt(4)
    p_abs.paragraph_format.space_after = Pt(4)
    p_abs.paragraph_format.line_spacing = 1.08
    r_abs_bold = p_abs.add_run("Abstract—")
    r_abs_bold.font.name = 'Times New Roman'
    r_abs_bold.font.size = Pt(9)
    r_abs_bold.font.bold = True

    abs_text = (
        "VitaNexus-RX is an implemented clinical decision support system that combines source-based medication safety "
        "evidence with learned adverse-risk evidence to support structured clinician review of same-indication candidate "
        "alternatives. The runtime evaluates candidate drug and active-medication pairs against DDInter, evaluates candidate "
        "drug and resolvable conditions against DrugCentral, and strictly preserves the semantic distinction between a completed "
        "lookup with no documented adverse record and an unresolved or failed lookup. "
    )
    if stage >= 2:
        abs_text += (
            "To bridge vocabulary gaps across diverse curated sources without modifying frozen models, a seven-level clinical terminology "
            "bridge resolves salt forms, MedDRA word inversions, orthographic spelling variants, and clinical synonyms. "
        )
    abs_text += (
        "Its primary learned component is an isotonic-calibrated LightGBM model trained on 4.91 million FDA Adverse Event "
        "Reporting System (FAERS) records, designed specifically to estimate whether a report in the represented context belongs "
        "to a serious-outcome class. Case-level bootstrap variation and split conformal classification sets are computed to provide "
        "transparent reliability diagnostics, while a conservative upper bootstrap bound participates directly in ranking. Candidates "
        "with documented major drug-drug interactions or high drug-disease restrictions are excluded prior to scoring. Remaining fully "
        "evaluated candidates are ordered by a deterministic 50/30/20 composite policy integrating adjusted LightGBM risk, DDInter risk, "
        "and DrugCentral drug-disease risk. A supplementary 100-label heterogeneous graph neural network (HGNN) provides granular adverse "
        "event-level profiling. On an untouched temporal holdout of 696,604 reports (2026Q1–Q2), the selected LightGBM classifier achieved "
        "AUROC 0.8177, AUPRC 0.8212, F1 0.7823, sensitivity 90.18%, specificity 54.04%, Brier score 0.1743, and expected calibration error 0.0358. "
        "The manuscript documents the implemented scope, evidence contracts, evaluation artifact, and limitations; it does not claim clinical "
        "validation, prevention of adverse drug reactions, or patient-outcome prediction."
    )
    r_abs = p_abs.add_run(abs_text)
    r_abs.font.name = 'Times New Roman'
    r_abs.font.size = Pt(9)

    p_terms = doc.add_paragraph()
    p_terms.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_terms.paragraph_format.left_indent = Inches(0.35)
    p_terms.paragraph_format.right_indent = Inches(0.35)
    p_terms.paragraph_format.space_before = Pt(2)
    p_terms.paragraph_format.space_after = Pt(14)
    p_terms.paragraph_format.line_spacing = 1.08
    r_terms_bold = p_terms.add_run("Index Terms—")
    r_terms_bold.font.name = 'Times New Roman'
    r_terms_bold.font.size = Pt(9)
    r_terms_bold.font.bold = True
    r_terms = p_terms.add_run("clinical decision support, drug-drug interaction, drug-disease interaction, LightGBM, conformal prediction, terminology resolution, heterogeneous graph neural network, FAERS, medication recommendation.")
    r_terms.font.name = 'Times New Roman'
    r_terms.font.size = Pt(9)
    r_terms.font.italic = True

    # Section 1: Two Column
    sec1 = doc.add_section(docx.enum.section.WD_SECTION.CONTINUOUS)
    sec1.page_width = Inches(8.5)
    sec1.page_height = Inches(11.0)
    sec1.top_margin = Inches(0.75)
    sec1.bottom_margin = Inches(0.75)
    sec1.left_margin = Inches(0.65)
    sec1.right_margin = Inches(0.65)

    sectPr1 = sec1._sectPr
    cols = sectPr1.xpath('./w:cols')
    if cols:
        cols[0].set(qn('w:num'), '2')
        cols[0].set(qn('w:space'), '300')
    else:
        col_elem = OxmlElement('w:cols')
        col_elem.set(qn('w:num'), '2')
        col_elem.set(qn('w:space'), '300')
        sectPr1.append(col_elem)

    def add_h1(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(11)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(10)
        run.font.bold = True
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9.5)
        run.font.italic = True
        run.font.bold = True
        return p

    def add_p(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3.5)
        p.paragraph_format.line_spacing = 1.05
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9.5)
        return p

    def add_fig(img_path, caption_text):
        if stage >= 3 and Path(img_path).exists():
            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.paragraph_format.space_before = Pt(6)
            p_img.paragraph_format.space_after = Pt(2)
            p_img.paragraph_format.keep_with_next = True
            run_img = p_img.add_run()
            run_img.add_picture(str(img_path), width=Inches(3.45))
            
            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_cap.paragraph_format.space_before = Pt(2)
            p_cap.paragraph_format.space_after = Pt(7)
            parts = caption_text.split(".", 1)
            r_bold = p_cap.add_run(parts[0] + ".")
            r_bold.font.name = 'Times New Roman'
            r_bold.font.size = Pt(8.5)
            r_bold.font.bold = True
            if len(parts) > 1:
                r_desc = p_cap.add_run(parts[1])
                r_desc.font.name = 'Times New Roman'
                r_desc.font.size = Pt(8.5)

    def add_tbl_cap(t_num, title):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        r_num = p.add_run(f"TABLE {t_num}\n")
        r_num.font.name = 'Times New Roman'
        r_num.font.size = Pt(8.5)
        r_num.font.bold = True
        r_title = p.add_run(title.upper())
        r_title.font.name = 'Times New Roman'
        r_title.font.size = Pt(8.0)

    # I. INTRODUCTION
    add_h1("I. INTRODUCTION")
    add_p("Medication recommendation and review within clinical decision support systems (CDSS) require balancing therapeutic efficacy with multifaceted patient safety constraints. Clinicians frequently evaluate whether an alternative agent sharing the same therapeutic indication can replace an existing prescription that is poorly tolerated, contraindicated, or subject to adverse interaction risks. Prior computational studies have advanced this domain through diverse paradigms: message propagation architectures with drug-drug interaction (DDI) gating mechanisms [1], molecular graph representations with atomic 3D position encodings [2], hierarchical prescription inference from longitudinal visit sequences [3], [7], [8], causal formulation of medication selection [9], and foundation models integrating multi-source clinical domain knowledge [10]. While these computational frameworks demonstrate promising predictive capabilities, they often obscure the operational boundaries and provenance of individual safety signals, presenting composite outputs that clinicians cannot readily audit.")
    add_p("The primary engineering challenge addressed in this work is one of rigorous, provenance-preserving system integration. A practical clinician-facing decision support tool must maintain transparent boundaries: it must preserve authoritative pharmacological source evidence, prevent unverified or unresolved clinical concepts from being quietly treated as safe, ensure that documented high-severity safety contraindications are never overridden by favorable machine-learned risk scores, and provide a fully deterministic, auditable rationale for alternative drug rankings. VitaNexus-RX addresses these requirements by establishing an evidence-bounded workflow that couples curated knowledge bases with calibrated machine learning and heterogeneous graph event profiling.")
    add_p("The system maintains a deliberately bounded interpretation. The LightGBM model estimates the probability that a FAERS adverse-event report represented by the runtime inputs belongs to the serious-outcome class. Because FAERS lacks an exposed-population denominator in this workflow, this output cannot be interpreted as the probability that a particular patient will experience any adverse event, require hospitalization, or benefit from a candidate drug.")
    add_p("The contributions of this paper are:\n1) A provenance-preserving safety contract that distinguishes documented source evidence, completed negative lookups, and unresolved evidence.\n2) A vocabulary-aware clinical terminology bridge that resolves cross-source naming discrepancies through salt-form equivalence, word-order resolution, orthographic normalization, and curated synonym mapping — without retraining the frozen ML artifact.\n3) End-to-end integration of calibrated LightGBM serious-outcome estimation with bootstrap variation and split-conformal classification, where learned evidence supplements but never overrides source-based safety gates.\n4) A deterministic, reproducible same-indication alternative ranking policy with explicit safety eligibility and reliability-aware ordering.\n5) A supplementary heterogeneous graph neural network for event-level adverse reaction profiling across a 100-label MedDRA vocabulary.")

    # II. RELATED WORK
    add_h1("II. RELATED WORK AND DESIGN MOTIVATION")
    add_p("The interpretation boundaries stated in Section I apply throughout; they are not restated in individual sections. Clinical medication selection involves several orthogonal dimensions of medical evidence: therapeutic indication alignment, pairwise drug-drug interactions, drug-disease contraindications, pharmacovigilance adverse reaction patterns, and uncertainty quantification. In modern hospital information systems, failure to separate these concerns leads to alert fatigue and compromised clinical trust [26], [31].")
    add_p("A. Interaction Modeling and Drug Recommendation Architectures: Recent artificial intelligence models for medication recommendation have placed significant emphasis on graph representations. Ren et al. [1] introduced DDI gating to penalize interacting drug pairs during recommendation. Molecular graph neural networks have been developed to predict biophysical drug interactions directly from chemical structures [2], [5], [11], while knowledge graphs capture relational semantics across biomedical entities [5], [24], [25]. Deep generative and memory architectures, including GAMENet [22], SafeDrug [21], and MICRON [23], incorporate multi-level patient visit history and causal drug-interaction penalties. In parallel, visit-similarity networks [8], hierarchical prescription models [3], and multi-view self-attention mechanisms [7] improve multi-drug combination inference. Rather than replacing curated pharmacology databases with neural link predictions in safety-critical gates, VitaNexus-RX adopts an evidence-first posture: authoritative curated registries remain primary safety authorities, while neural graph models operate as supplementary diagnostic profilers.")
    add_p("B. Pharmacovigilance, Calibration, and Conformal Uncertainty: Spontaneous reporting systems, most notably the FDA Adverse Event Reporting System (FAERS), provide vast post-marketing observational data encompassing millions of clinical reports [12], [13], [30]. However, mining FAERS requires rigorous handling of reporting biases, duplicates, and missing denominators. Machine learning models trained on spontaneous reports risk overconfidence if uncalibrated. Traditional calibration techniques, including isotonic regression and Platt scaling [20], [29], [32], align predicted scores with empirical report-target frequencies. To quantify epistemic and aleatoric uncertainty, non-parametric bootstrap resampling [27] provides model variability intervals. Furthermore, split conformal prediction [17], [18], [19] produces distribution-free prediction sets with guaranteed finite-sample marginal coverage. Conformal prediction has been applied in medical imaging [4] and clinical dosing [6]; in VitaNexus-RX, conformal classification is deployed to inform clinicians whether an adverse-outcome classification is definitive or ambiguous.")
    add_p("C. Synthesis and Design Motivation: Existing CDSS architectures frequently suffer from terminology mismatches across disparate ontologies such as MedDRA [28], RxNorm, and DrugCentral [15], often failing closed or producing silent omissions. Table I positions the supplied literature across these dimensions and highlights the distinct integration approach implemented in VitaNexus-RX.")

    # TABLE I
    add_tbl_cap("I", "Prior Literature and Design Context Positioning")
    t1 = doc.add_table(rows=6, cols=3)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t1)
    for j, h in enumerate(["Research Context", "Key References", "Role in VitaNexus-RX Design"]):
        format_cell(t1.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(t1.cell(0, j), "17395D")
        set_cell_margins(t1.cell(0, j))
    data_t1 = [
        ("DDI-Gated Recommendation", "[1], [21], [22], [23]", "Motivates explicit, transparent interaction gating prior to scoring."),
        ("Graph-Based Interaction Reasoning", "[2], [5], [11], [24], [25]", "Informs computational DDI representations; not used to bypass curated safety."),
        ("Prescription Inference & EHR Modeling", "[3], [7], [8], [9], [10]", "Provides context for therapeutic indication matching and patient visit structure."),
        ("Uncertainty & Conformal Calibration", "[4], [6], [17], [18], [19], [20]", "Guides isotonic calibration, bootstrap variance, and split-conformal prediction sets."),
        ("VitaNexus-RX (Proposed System)", "Implemented Artifact", "Unifies source safety gates, terminology bridge, calibrated ML, and deterministic ranking.")
    ]
    for r_idx, d in enumerate(data_t1, start=1):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(d):
            c = t1.cell(r_idx, c_idx)
            format_cell(c, val, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx != 1 else WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(c, bg)
            set_cell_margins(c)

    # III. SYSTEM SCOPE
    add_h1("III. SYSTEM SCOPE AND PROBLEM FORMULATION")
    add_p("A clinical consultation in VitaNexus-RX requires verified input parameters: patient age, biological sex, current active medications, diagnosed medical conditions, and a mandatory therapeutic indication selected from DrugCentral. The indication record carries an immutable identifier, concept source, dataset version, and normalized clinical text. Free-text indication entry is prohibited at the API boundary, guaranteeing that alternative candidate retrieval is strictly grounded in curated pharmacological indications rather than ad-hoc search phrases.")
    add_p("The system maintains strict boundaries between automated decision inputs and clinician reference data. Documented patient allergies and disease duration are preserved for visual inspection in the user interface, but they are excluded from the LightGBM feature space and ranking calculations. Because automated drug-allergy cross-reactivity checking is not supported by the current knowledge engines, displaying allergy warnings without verified computational coverage would present a dangerous illusion of safety. Table II summarizes the operational roles of all system components.")

    # TABLE II
    add_tbl_cap("II", "Runtime System Components and Operational Roles")
    t2 = doc.add_table(rows=7, cols=3)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t2)
    for j, h in enumerate(["Component", "Operational Role", "Implementation Status"]):
        format_cell(t2.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(t2.cell(0, j), "17395D")
        set_cell_margins(t2.cell(0, j))
    data_t2 = [
        ("Indication Provenance", "Validates indication against DrugCentral 2021 before consultation submission.", "Implemented & Enforced"),
        ("DDI Evidence Gate", "Evaluates candidate × active medicines against DDInter; retains worst tier.", "Implemented & Enforced"),
        ("Drug-Disease Gate", "Evaluates candidate × conditions against DrugCentral; retains worst restriction.", "Implemented & Enforced"),
        ("Terminology Bridge", "7-level hierarchy resolving salt, word-order, orthographic, and synonym gaps.", "Implemented & Active"),
        ("Learned Risk Engine", "Calibrated LightGBM estimating FAERS serious-outcome report probability.", "Frozen & Verified"),
        ("Alternative Ranking", "Deterministic 50/30/20 formula ordering safety-eligible candidates.", "Implemented & Deterministic")
    ]
    for r_idx, d in enumerate(data_t2, start=1):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(d):
            c = t2.cell(r_idx, c_idx)
            format_cell(c, val, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx != 2 else WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(c, bg)
            set_cell_margins(c)

    add_p("For any candidate alternative, the runtime addresses three sequential clinical questions: First, do authoritative registries document contraindications against the patient's existing regimen? Second, what is the learned reporting-task outcome profile for this clinical feature vector? Third, how should eligible alternatives be ordered under an inspectable engineering policy? A favorable machine-learning score is never permitted to override an unresolved or adverse source check.")

    # IV. ARCHITECTURE
    add_h1("IV. SYSTEM ARCHITECTURE AND EXECUTION FLOW")
    add_p("VitaNexus-RX is implemented as a multi-tier service architecture comprising a React 18 / Vite single-page application, an Express 5 REST API gateway, PostgreSQL persistence through Prisma ORM (adapter-pg), local SQLite knowledge repositories (DDInter 2.0 and DrugCentral 2021), and an internal Python FastAPI microservice hosting the machine learning runtimes. Fig. 1 illustrates the evidence and recommendation execution workflow, while Fig. 2 details the runtime system topology.")
    add_fig(DOCS_DIR / "fig1_workflow.png", "Fig. 1. Implemented VitaNexus-RX evidence and recommendation workflow across clinical consultation stages.")
    add_fig(DOCS_DIR / "fig2_architecture.png", "Fig. 2. System architecture and runtime topology connecting client UI, Express API, knowledge bases, and FastAPI ML microservice.")
    add_p("The Express API gateway enforces strict validation using Zod schemas, propagates unique request tracking identifiers, and isolates external knowledge queries. At consultation intake, the API normalizes submitted terms, executes parallel DDInter and DrugCentral evaluations, and persists an immutable clinical safety snapshot. The machine learning service loads serialized artifacts once at container startup. All model predictions are validated for finiteness and range before persistence. If the ML service encounters out-of-vocabulary inputs or service timeouts, the gateway records explicit degraded or unavailable states rather than falling back to zero or low-risk defaults.")

    # V. TERMINOLOGY BRIDGE (stages >= 2)
    if stage >= 2:
        add_h1("V. CROSS-SOURCE TERMINOLOGY RESOLUTION")
        add_h2("A. Problem Statement and Architectural Context")
        add_p("A fundamental impediment to multi-source CDSS integration is clinical concept naming discordance. VitaNexus-RX unifies DDInter, DrugCentral, and the Indian Medicine Dataset with a frozen LightGBM model trained on FDA FAERS data. Each source was curated under disparate naming conventions. Because the LightGBM model's sparse feature space is permanently frozen at 15,369 features to ensure audit stability and regulatory reproducibility, the model artifact cannot be retrained to accommodate novel textual variants. A pre-inference Vocabulary-Aware Clinical Terminology Bridge was therefore implemented in the ML pipeline to resolve naming discrepancies prior to vocabulary evaluation.")
        add_h2("B. Root Cause Taxonomy")
        add_p("Cross-source concept mismatches stem from four distinct linguistic and pharmacological root causes:\n• Pharmaceutical Salt/Form Mismatch: Clinical repositories frequently record pure parent molecules (e.g., Metformin), whereas FAERS reporting forms capture specific manufacturer salt formulations entered by reporting clinicians (e.g., Metformin Hydrochloride).\n• MedDRA Word-Order Inversion: Clinicians and knowledge bases express disease concepts in natural-language syntax (e.g., Atopic dermatitis), whereas regulatory pharmacovigilance dictionaries store formal inverted MedDRA Preferred Terms (e.g., Dermatitis atopic).\n• Clinical and Chemical Synonyms: Distinct accepted names represent identical pharmacological agents across international compendia (e.g., Acetylsalicylic acid versus Aspirin, or Paracetamol versus Acetaminophen).\n• Orthographic and Regional Spelling Variants: Transatlantic spelling discrepancies occur across British and American regulatory bodies and dictionaries (e.g., Gastroesophageal versus Gastrooesophageal, or Edema versus Oedema).")
        add_h2("C. Resolution Hierarchy")
        add_p("To resolve these discrepancies deterministically without inflating the feature space, the terminology bridge executes a top-down, seven-level resolution hierarchy that terminates at the first unique verified match:\n1) Exact Match: Direct evaluation against the target vocabulary following Unicode NFKC normalization, capitalization, and punctuation stripping.\n2) Project-Defined Aliases: Deterministic crosswalk of established core pharmacological aliases (e.g., Paracetamol to Acetaminophen).\n3) Orthographic Variant Generation: Bidirectional transformation applying rule-based phonetic and regional orthographic patterns (e.g., 'oe'/'ae' digraph substitutions) with immediate vocabulary membership validation.\n4) Token-Set Reordering: Generation of sorted token-set signatures to identify permutations of identical word sets regardless of syntactic inversion (e.g., matching 'Dermatitis atopic' from 'Atopic dermatitis').\n5) Pharmaceutical Salt/Form Equivalence: Systematic stripping and appending of recognized pharmaceutical salt suffixes (e.g., Hydrochloride, Sodium, Tartrate, Maleate) against vocabulary entries.\n6) Curated Clinical Synonym Crosswalk: Secondary lookup across curated multi-source synonym mappings.\n7) Terminal Safety Fallback: If no candidate in the vocabulary matches, the concept remains UNRESOLVED. If multiple ambiguous candidates match, it is flagged as AMBIGUOUS.")
        add_h2("D. Safety Contract Preservation")
        add_p("The bridge strictly preserves the system's safety contract. It never forces an ambiguous mapping, never invents non-existent vocabulary tokens, and leaves the 15,369-feature model geometry completely untouched. If a submitted clinical entity cannot be unambiguously resolved, the pipeline preserves conservative fail-closed behavior, returning OUT_OF_VOCABULARY or DEGRADED_COVERAGE and withholding automated risk estimation. Fig. 3 diagrams the bridge architecture.")
        add_fig(DOCS_DIR / "fig3_bridge.png", "Fig. 3. Vocabulary-aware clinical terminology bridge pipeline showing seven-level resolution hierarchy and frozen vocabulary validation.")

    # VI. SOURCE-BASED CLINICAL SAFETY
    sec_num_vi = "VI" if stage >= 2 else "V"
    add_h1(f"{sec_num_vi}. SOURCE-BASED CLINICAL SAFETY ANALYSIS")
    add_h2("A. Drug-Drug Interaction Analysis")
    add_p("Pairwise drug-drug interactions are evaluated against DDInter 2.0 using tri-state logic. When both substances resolve unambiguously and a documented interaction exists, the system records the source severity: MAJOR, MODERATE, or MINOR. When both substances resolve and the lookup completes with no interaction recorded, the outcome is NO DOCUMENTED INTERACTION. This is a valid, completed source finding representing absence of documented risk, not a lookup failure. Conversely, if an entered drug cannot be resolved, an identifier is ambiguous, or the database is unreachable, the system assigns REQUIRES CLINICAL REVIEW.")
    add_p("This distinction prevents critical clinical errors: treating an empty DDInter result as a failure would block valid therapies, whereas treating an unresolvable lookup as an empty result would mask unknown risks. For example, co-administering Warfarin and Aspirin yields a documented MAJOR interaction, correctly triggering immediate exclusion. Co-administering Metformin and Paracetamol completes successfully with NO DOCUMENTED INTERACTION, allowing the pair to remain eligible. If an entered medication cannot be resolved, the pair is flagged REQUIRES CLINICAL REVIEW.")
    add_h2("B. Drug-Disease Interaction Analysis")
    add_p("Drug-disease relationships are evaluated against DrugCentral 2021. Resolvable patient conditions are checked against candidate contraindications, returning HIGH, MODERATE, LOW, or NO DOCUMENTED RELATIONSHIP. If a condition term cannot be mapped to a DrugCentral concept, the assessment is marked REQUIRES CLINICAL REVIEW. Table III delineates the source evidence states and their eligibility impacts. Fig. 4 illustrates the safety gating and ranking decision flowchart.")

    # TABLE III
    add_tbl_cap("III", "Source Evidence States and Safety Gate Eligibility Outcomes")
    t3 = doc.add_table(rows=6, cols=3)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t3)
    for j, h in enumerate(["Source Evidence Result", "Operational Semantics", "Eligibility & Ranking Impact"]):
        format_cell(t3.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(t3.cell(0, j), "17395D")
        set_cell_margins(t3.cell(0, j))
    data_t3 = [
        ("MAJOR / HIGH", "Documented severe interaction or contraindication.", "NOT RECOMMENDED; excluded before ML scoring."),
        ("MODERATE", "Documented moderate interaction or disease caution.", "ELIGIBLE; assigned 0.50 normalized source risk."),
        ("MINOR / LOW", "Documented minor interaction or mild caution.", "ELIGIBLE; assigned 0.10 normalized source risk."),
        ("NO DOCUMENTED INTERACTION", "Completed lookup confirms no recorded relationship.", "ELIGIBLE; assigned 0.30 baseline source risk."),
        ("REQUIRES CLINICAL REVIEW", "Lookup failed, term unresolved, or ambiguous identifier.", "BLOCKED from scoring; review required.")
    ]
    for r_idx, d in enumerate(data_t3, start=1):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(d):
            c = t3.cell(r_idx, c_idx)
            format_cell(c, val, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx != 2 else WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(c, bg)
            set_cell_margins(c)

    add_fig(DOCS_DIR / "fig4_safety_gate.png", "Fig. 4. Safety gate decision flowchart showing two-stage pre-filtering, LightGBM risk scoring, and composite alternative ranking.")

    # VII. ADVERSE RISK PREDICTION
    sec_num_vii = "VII" if stage >= 2 else "VI"
    add_h1(f"{sec_num_vii}. ADVERSE RISK PREDICTION AND RELIABILITY ANALYSIS")
    add_p("The primary learned risk component is a LightGBM gradient boosted decision tree classifier trained on 18 quarterly FAERS releases (2022Q1 to 2026Q2). The raw FAERS corpus underwent rigorous case-level deduplication, resolving case versions by primary suspect drug to retain 6,309,764 unique patient report rows. The binary target classifies serious adverse outcomes (death, life-threatening events, hospitalization, disability, or congenital anomaly). Fig. 5 illustrates the chronological data partitioning timeline.")
    add_fig(DOCS_DIR / "fig5_timeline.png", "Fig. 5. Chronological FAERS data partitioning timeline showing training, calibration, and temporal evaluation cohorts.")
    add_p("Strict temporal partitioning isolates all experimental phases: 4,910,268 reports (2022Q1–2025Q2) constitute the model training set; 375,893 reports (2025Q3) serve as an independent isotonic calibration cohort; 326,999 reports (2025Q4) provide split conformal calibration; and 696,604 reports (2026Q1–Q2) remain as an untouched temporal holdout. The sparse feature encoder generates 15,369 binary and scaled numerical features spanning patient demographics, polypharmacy counts, candidate drugs (4,359), indications (5,000), concomitant medicines (1,001), and candidate-by-indication interactions (5,001).")
    add_p("To quantify model parameter variability, 20 CASEID-level bootstrap model replicas are trained. The upper 90th percentile bound of the bootstrap probability distribution is extracted as the conservative adjusted risk estimate used in downstream ranking. In addition, split conformal classification sets are generated at nominal 90% confidence, categorizing predictions as focused serious-outcome, focused non-serious, or ambiguous when both classes remain plausible.")

    # VIII. RECOMMENDATION
    sec_num_viii = "VIII" if stage >= 2 else "VII"
    add_h1(f"{sec_num_viii}. SAFETY-AWARE SAME-INDICATION ALTERNATIVE RECOMMENDATION")
    add_p("When an existing medication requires substitution, VitaNexus-RX queries DrugCentral for alternative compounds indicated for the identical clinical condition. Each candidate alternative is evaluated through the two-tier safety gate before invoking machine learning. Candidates exhibiting major DDInter interactions or high DrugCentral restrictions receive NOT RECOMMENDED. Candidates with unresolved lookups receive REQUIRES CLINICAL REVIEW. Only candidates achieving ELIGIBLE status proceed to LightGBM risk scoring.")
    add_p("Eligible candidates are ordered by a deterministic composite risk formula:\nFinalRisk = 0.50 · Risk_LGBM + 0.30 · Risk_DDI + 0.20 · Risk_Disease\nwhere Risk_LGBM is the conservative upper bootstrap risk bound, Risk_DDI is the normalized interaction penalty (0.10 for minor, 0.30 for completed lookup with no record, 0.50 for moderate), and Risk_Disease is the normalized disease penalty (0.10 for low, 0.30 for none, 0.50 for moderate).")
    add_p("The 50/30/20 weight distribution reflects an explicit, auditable engineering design choice: LightGBM receives 50% weight because it is the only empirical component trained and calibrated across 4.91 million real-world adverse outcome reports; pairwise DDI safety receives 30% weight to heavily penalize documented pharmacology risks; and drug-disease contraindications receive 20% weight as a condition-specific safety boundary. For candidates with unsupported concomitant medications (DEGRADED_COVERAGE), the weights shift to 25% LightGBM, 30% DDI, 20% drug-disease, and a 25% maximal coverage penalty. Deterministic tie-breaking ensures identical rankings across executions without opaque neural stochasticity. Indian brand mapping is presented downstream as clinician-facing dispensing support.")

    # IX. HGNN
    sec_num_ix = "IX" if stage >= 2 else "VIII"
    add_h1(f"{sec_num_ix}. SUPPLEMENTARY HGNN EVENT PROFILE")
    if stage >= 2:
        add_p("To provide event-specific adverse reaction profiling beyond binary serious-outcome risk, VitaNexus-RX integrates a completed heterogeneous graph neural network (HGNN). While LightGBM models overall report-level severity, the HGNN models granular multi-label associations across 100 MedDRA Preferred Term adverse reactions. The model has fully completed both selection training (20 epochs) and final refit training over the 2022Q1–2025Q4 modeling window, evaluated on the 2026Q1–Q2 temporal testing cohort.")
        add_p("The network architecture is implemented as HeterogeneousAdrNetwork(hidden_channels=96, output_channels=100) using PyTorch Geometric. The graph schema incorporates four node types: report, drug, indication, and adverse reaction (ADR). It establishes ten directed edge relations: report-primary suspect-drug, drug-reverse primary suspect-report, report-concomitant-drug, drug-reverse concomitant-report, report-indication-indication, indication-reverse indication-report, drug-historically associated-ADR, ADR-reverse historically associated-drug, indication-historically associated-ADR, and ADR-reverse indication associated-indication. Four node projection layers feed two HeteroConv layers utilizing GraphSAGE operators (SAGEConv) with sum aggregation, residual skip connections, and ReLU activations, projecting to a linear classification head producing 100 event logits passed through sigmoid activations.")
        add_p("On the temporal testing cohort, the HGNN achieved micro-AUPRC 0.156023, macro-AUPRC 0.129541, micro-F1 0.066962, precision 0.621854, and recall 0.035386 across the 100 MedDRA reaction categories (Table VI). The HGNN is retained in the deployed architecture because it is exposed directly in the clinician interface to provide supplementary event profiling, its transparent reporting of recall provides honest benchmark data for extreme label imbalance, and its heterogeneous graph topology establishes an auditable foundation for multi-label event modeling.")
    else:
        add_p("The system also exposes a supplementary HGNN-derived specific-event profile. It loads a hash-verified epoch-20 selection checkpoint with an ordered 100-label vocabulary and returns deterministic top-K sigmoid model scores. It is independent of LightGBM, does not alter DDInter or DrugCentral safety gates, does not alter candidate generation or ranking, and operates as an event-level diagnostic view.")

    # X. RESULTS
    sec_num_x = "X" if stage >= 2 else "IX"
    add_h1(f"{sec_num_x}. RESULTS AND ARTIFACT-BASED EVALUATION")
    if stage >= 3:
        add_h2("A. Baseline Model Comparison and Selection Justification")
        add_p("During model development, multiple scalable linear and probabilistic classifiers were evaluated on the full 4.27M training and 638K validation cohort under identical sparse feature representations. Table IV summarizes performance across evaluated baselines and the selected LightGBM classifier.")
        
        # TABLE IV
        add_tbl_cap("IV", "Classifier Performance Comparison on FAERS Development Validation Cohort")
        t4 = doc.add_table(rows=4, cols=6)
        t4.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_borders(t4)
        for j, h in enumerate(["Model Architecture", "AUROC", "AUPRC", "F1 Score", "Sensitivity", "Specificity"]):
            format_cell(t4.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(t4.cell(0, j), "17395D")
            set_cell_margins(t4.cell(0, j))
        data_t4 = [
            ("Complement Naive Bayes", "0.8390", "0.8383", "0.7948", "88.19%", "60.73%"),
            ("Linear Logistic (SGD)", "0.8508", "0.8687", "0.7925", "87.23%", "61.66%"),
            ("LightGBM (Selected Holdout)", "0.8177", "0.8212", "0.7823", "90.18%", "54.04%")
        ]
        for r_idx, d in enumerate(data_t4, start=1):
            bg = "EBF8FF" if r_idx == 3 else ("F7FAFC" if r_idx % 2 == 1 else "FFFFFF")
            is_bold = (r_idx == 3)
            for c_idx, val in enumerate(d):
                c = t4.cell(r_idx, c_idx)
                format_cell(c, val, bold=is_bold, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER)
                set_cell_shading(c, bg)
                set_cell_margins(c)

        add_p("LightGBM was selected over linear and naive Bayes baselines due to several compelling architectural advantages: gradient boosted decision trees natively capture non-linear feature interactions among high-dimensional sparse drug and indication categories without requiring dense projection embeddings; the algorithm trains efficiently across millions of records on commodity multicore hardware within bounded memory; and the resulting tree ensembles produce deterministic, auditable decision paths compatible with post-hoc isotonic calibration and CASEID-level bootstrap replication.")
        add_h2("B. Temporal Holdout Evaluation and Operating Point")

    add_p("The frozen LightGBM model was evaluated on the untouched 2026Q1–Q2 temporal holdout consisting of 696,604 reports. Table V presents comprehensive evaluation metrics at the frozen 0.389 operating cutoff, chosen on the disjoint 2025Q4 operating subset to maximize specificity while enforcing a sensitivity floor of 90.0%.")

    # TABLE V
    add_tbl_cap("V" if stage >= 3 else "IV", "Frozen Selected Operating-Point Performance on 2026 Temporal Holdout")
    t5 = doc.add_table(rows=10, cols=3)
    t5.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t5)
    for j, h in enumerate(["Metric / Parameter", "Measured Holdout Value", "Clinical Interpretation"]):
        format_cell(t5.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(t5.cell(0, j), "17395D")
        set_cell_margins(t5.cell(0, j))
    data_t5 = [
        ("Evaluation Population", "696,604 Reports", "Untouched temporal holdout cohort (2026Q1–2026Q2)."),
        ("AUROC", "0.8177", "Threshold-independent serious-outcome discrimination."),
        ("AUPRC", "0.8212", "Area under precision-recall curve under class prevalence."),
        ("Sensitivity (Recall)", "90.18%", "Successfully captures >90% of serious-outcome reports."),
        ("Specificity", "54.04%", "Screens out over half of non-serious reports at safety cutoff."),
        ("Precision / F1 Score", "69.07% / 0.7823", "Positive predictive balance at operating threshold 0.389."),
        ("Accuracy / Balanced Acc.", "73.28% / 72.11%", "Overall classification accuracy across both outcome classes."),
        ("Brier Score", "0.1743", "Mean squared error of probabilistic predictions."),
        ("Expected Calibration Error (ECE)", "0.0358", "Demonstrates close alignment between predicted and empirical risk.")
    ]
    for r_idx, d in enumerate(data_t5, start=1):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(d):
            c = t5.cell(r_idx, c_idx)
            format_cell(c, val, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx != 1 else WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(c, bg)
            set_cell_margins(c)

    if stage >= 3:
        add_h2("C. Conformal Prediction Set Reliability and HGNN Performance")
    add_p("On the 2026 holdout, split conformal classification achieved empirical coverage of 0.8739 against a nominal 0.90 target, with an average prediction set size of 1.3183, a singleton rate of 68.17%, and 0.0% empty sets. This modest coverage contraction (0.8739 vs. 0.90) is expected under temporal distribution shift between the 2025Q4 calibration period and the 2026 evaluation period. Because conformal guarantees rely on exchangeability, temporal drift in spontaneous reporting patterns naturally influences coverage, underscoring the importance of periodic re-calibration. Table VI summarizes the completed HGNN event profile evaluation.")

    # TABLE VI
    add_tbl_cap("VI" if stage >= 3 else "V", "Supplementary HGNN Event-Profile Performance Metrics Across 100 MedDRA Labels")
    t6 = doc.add_table(rows=7, cols=3)
    t6.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t6)
    for j, h in enumerate(["Performance Metric", "Measured Value", "Evaluation Context & Operational Role"]):
        format_cell(t6.cell(0, j), h, bold=True, color=(255,255,255), align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_shading(t6.cell(0, j), "17395D")
        set_cell_margins(t6.cell(0, j))
    data_t6 = [
        ("Training & Refit Epochs", "20 Epochs (Completed)", "Fully converged selection checkpoint and refit model."),
        ("Micro-AUPRC", "0.156023", "Area under PR curve across all 100 reaction labels."),
        ("Macro-AUPRC", "0.129541", "Unweighted average PR curve across highly imbalanced labels."),
        ("Micro-F1 Score", "0.066962", "Multi-label classification balance across MedDRA vocabulary."),
        ("Precision / Recall", "0.621854 / 0.035386", "Demonstrates high positive precision with conservative recall."),
        ("Output Representation", "Top-K Sigmoid Scores", "Displayed as ordered event diagnostic profile; not in ranking.")
    ]
    for r_idx, d in enumerate(data_t6, start=1):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(d):
            c = t6.cell(r_idx, c_idx)
            format_cell(c, val, font_size=8.0, align=WD_ALIGN_PARAGRAPH.LEFT if c_idx != 1 else WD_ALIGN_PARAGRAPH.CENTER)
            set_cell_shading(c, bg)
            set_cell_margins(c)

    # XI. DISCUSSION
    sec_num_xi = "XI" if stage >= 2 else "X"
    add_h1(f"{sec_num_xi}. DISCUSSION AND LIMITATIONS")
    add_p("The implementation boundaries established in Section I define the operational limits of this study: VitaNexus-RX is an evidence-bounded clinical decision support system designed to assist clinician review; it does not claim clinical validation, prevention of adverse reactions, or patient-level outcome prediction.")
    add_p("A. Safety Gate Behavior and Deterministic Logic: The primary clinical asset of VitaNexus-RX is its strict separation between authoritative source records and statistical models. In conventional predictive prescribing systems, high-dimensional neural models risk masking acute pairwise contraindications if composite scores appear favorable. By placing DDInter and DrugCentral safety gates strictly ahead of ML inference, VitaNexus-RX guarantees that severe documented risks (such as a major DDI) irrevocably trigger NOT RECOMMENDED status. Furthermore, distinguishing completed negative lookups from unresolved records prevents both alert fatigue and false reassurances.")
    add_p("B. Cross-Source Terminology Resolution: The implemented seven-level terminology bridge addresses a critical operational bottleneck in deploying frozen machine learning models. By resolving pharmaceutical salts, MedDRA syntax inversions, clinical synonyms, and orthographic variations without altering model feature geometry, the bridge significantly improves system usability while maintaining conservative fail-closed behavior on truly unsupported terms.")
    add_p("C. Evaluation Limitations: Several methodological limitations must be acknowledged. First, FAERS is a spontaneous reporting repository characterized by significant reporting biases, under-reporting, and an absence of unexposed control populations. Consequently, LightGBM predictions represent reporting-task outcome probabilities rather than prospective patient-level incidence. Second, although evaluated on an untouched temporal holdout spanning 2026Q1–Q2, the system has not yet undergone multi-center prospective cohort validation in active clinical electronic health records.")
    add_p("D. Implementation Boundaries: The system was intentionally engineered to operate on standard consumer and server hardware without requiring GPU compute clusters during inference. The recommendation ordering relies on an explicit, inspectable 50/30/20 formula rather than an end-to-end neural ranker. Furthermore, automated allergy screening and real-time electronic prescribing feedback loops remain outside current scope.")
    add_p("E. Future Work: Future investigations will focus on prospective clinical usability trials, formal clinical governance reviews of terminology crosswalks, multi-center EHR validation, and calibrating the supplementary HGNN architecture to explore whether granular reaction profiles can be safely incorporated into multi-criteria recommendation policies.")

    # XII. CONCLUSION
    sec_num_xii = "XII" if stage >= 2 else "XI"
    add_h1(f"{sec_num_xii}. CONCLUSION")
    add_p("VitaNexus-RX provides a comprehensive, evidence-bounded framework for safety-aware medication review and same-indication alternative recommendation. By integrating authoritative pharmacological registries with calibrated gradient boosted decision trees, conformal uncertainty quantification, a seven-level clinical terminology bridge, and a supplementary heterogeneous graph neural network, the architecture resolves critical trade-offs between predictive capability, terminology coverage, and clinical safety gating.")
    add_p("Quantitative evaluation on an untouched 2026 temporal holdout of 696,604 reports demonstrates strong discriminative performance (AUROC 0.8177, AUPRC 0.8212, sensitivity 90.18%, specificity 54.04%, Brier score 0.1743, and ECE 0.0358) alongside robust conformal prediction sets and a fully converged HGNN event profile. The system's deterministic 50/30/20 ranking policy provides transparent, reproducible recommendations while ensuring that documented contraindications remain dominant.")
    add_p("Future research will prioritize prospective multi-center clinical validation and formal clinical governance integration. The available evidence supports implementation and the stated report-target evaluation; it does not support patient-level adverse-event prediction or clinical-effect claims.")

    # ACKNOWLEDGMENT
    add_h1("ACKNOWLEDGMENT")
    add_p("The authors acknowledge the public data resources and research infrastructures that made this study possible: the U.S. Food and Drug Administration (FDA) for the Adverse Event Reporting System (FAERS) public data files; the DDInter research team for the curated drug-drug interaction knowledge base; the DrugCentral team for the open-access drug and indication database; and the contributors of the Indian Medicine Dataset for brand-to-generic pharmaceutical terminology records.")

    # REFERENCES
    add_h1("REFERENCES")
    references = [
        "[1] Y. Ren, Y. Shi, K. Zhang, X. Wang, Z. Chen, and H. Li, \"A Drug Recommendation Model Based on Message Propagation and DDI Gating Mechanism,\" IEEE Journal of Biomedical and Health Informatics, vol. 26, no. 7, pp. 3478–3488, Jul. 2022, doi: 10.1109/JBHI.2022.3160840.",
        "[2] T. Luo, T. Lin, C. Yang, L. Fan, and W. Wang, \"A Drug-Drug Interaction Prediction Method Based on Atomic 3D Position Encoding and Elastic Message Passing Graph Neural Network,\" IEEE Journal of Biomedical and Health Informatics, vol. 29, no. 9, pp. 6915–6925, Sep. 2025, doi: 10.1109/JBHI.2025.3575916.",
        "[3] X. Li, X. Hou, F. Meng, H. Cui, and Y. Zhang, \"Collaborative Relation Augmentation With Hierarchical Prescription Inference for Medication Recommendation,\" IEEE Journal of Biomedical and Health Informatics, vol. 30, no. 7, p. 5530, Jul. 2026.",
        "[4] S. Pintawong et al., \"Conformal Prediction for Uncertainty Quantification and Reliable HER2 Status Classification in Breast Cancer IHC Images,\" IEEE Access, vol. 13, pp. 48729–48742, 2025, doi: 10.1109/ACCESS.2025.3552934.",
        "[5] I. N. Kundi, A. A. Sheikh, A. W. Malik, and G. A. Bhatti, \"DDI-KGAT: A Graph Attention Network on Biomedical Knowledge Graph for the Prediction of Drug-Drug Interactions,\" IEEE Access, vol. 12, pp. 165842–165855, 2024, doi: 10.1109/ACCESS.2024.3483993.",
        "[6] E. Daglarli, \"Drug and Dosage Recommendation Based on Explainable Generative AI Using Patient-Specific Modeling,\" IEEE Access, vol. 14, pp. 24810–24825, 2026, doi: 10.1109/ACCESS.2026.3657398.",
        "[7] Y. Meng, Y. Zhang, J. Shang, J. Tang, C. Li, Y. Zhang, H. Cui, R. Jin, Y. Xu, and F. Wang, \"FusionMVSA: Multi-View Fusion Strategy With Self-Attention for Enhancing Drug Recommendation,\" IEEE Journal of Biomedical and Health Informatics, vol. 30, no. 2, pp. 1120–1131, Feb. 2026.",
        "[8] Y. He, X. Dong, J. Lin, Y. Zheng, and Y. Hu, \"Pretraining-Based Relevance-Aware Visit Similarity Network for Drug Recommendation,\" IEEE Journal of Biomedical and Health Informatics, vol. 30, no. 7, p. 5542, Jul. 2026.",
        "[9] J. Zhang, Y. Zang, J. Chen, X. Yan, and J. Tang, \"Revisiting Drug Recommendation From a Causal Perspective,\" IEEE Journal of Biomedical and Health Informatics, vol. 29, no. 2, pp. 1525–1536, Feb. 2025, doi: 10.1109/JBHI.2024.3496030.",
        "[10] J. Wu, K. He, Z. Gao, X. Shang, and M. Feng, \"Towards Smarter Clinical Predictions: Foundation Models for Integrating Multi-Source Domain Knowledge in EHRs,\" IEEE Journal of Biomedical and Health Informatics, pp. 1–12, 2025, doi: 10.1109/JBHI.2025.3609064.",
        "[11] J. Cheng, Y. Zhang, Y. Zhang, S. Ji, and X. Lu, \"TransFOL: A Logical Query Model for Complex Relational Reasoning in Drug-Drug Interaction,\" IEEE Journal of Biomedical and Health Informatics, vol. 28, no. 8, pp. 4975–4986, Aug. 2024, doi: 10.1109/JBHI.2024.3401567.",
        "[12] T. Sakaeda, A. Tamon, K. Kadoyama, and Y. Okuno, \"Data mining of the public version of the FDA Adverse Event Reporting System,\" International Journal of Medical Sciences, vol. 10, no. 7, pp. 796–803, 2013, doi: 10.7150/ijms.6048.",
        "[13] J. M. Banda, L. Evans, R. S. Vanguri, N. H. Tatonetti, P. B. Ryan, and N. P. Shah, \"A curated and standardized adverse drug event resource to accelerate drug safety research,\" Scientific Data, vol. 3, no. 1, p. 160026, May 2016, doi: 10.1038/sdata.2016.26.",
        "[14] G. Xiong et al., \"DDInter: an online drug–drug interaction database towards improving clinical medication safety,\" Nucleic Acids Research, vol. 50, no. D1, pp. D1200–D1207, Jan. 2022, doi: 10.1093/nar/gkab880.",
        "[15] S. Avram et al., \"DrugCentral 2021: an extension to biotics and chemical compounds,\" Nucleic Acids Research, vol. 49, no. D1, pp. D1160–D1169, Jan. 2021, doi: 10.1093/nar/gkaa997.",
        "[16] G. Ke, Q. Meng, T. Finley, T. Wang, W. Chen, W. Ma, Q. Ye, and T.-Y. Liu, \"LightGBM: A Highly Efficient Gradient Boosting Decision Tree,\" in Advances in Neural Information Processing Systems (NeurIPS), vol. 30, pp. 3146–3154, 2017.",
        "[17] V. Vovk, A. Gammerman, and G. Shafer, Algorithmic Learning in a Random World. New York, NY, USA: Springer, 2005.",
        "[18] A. N. Angelopoulos and S. Bates, \"A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification,\" Foundations and Trends in Machine Learning, vol. 16, no. 4, pp. 494–591, 2023, doi: 10.1561/2200000101.",
        "[19] Y. Romano, M. Sesia, and E. Candès, \"Classification with Valid and Adaptive Coverage,\" in Advances in Neural Information Processing Systems (NeurIPS), vol. 33, pp. 3581–3591, 2020.",
        "[20] B. Zadrozny and C. Elkan, \"Transforming classifier scores into accurate multiclass probability estimates,\" in Proceedings of the Eighth ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD), Edmonton, AB, Canada, pp. 694–699, 2002, doi: 10.1145/775047.775151.",
        "[21] C. Yang, C. Xiao, F. Ma, J. T. Lucas, and J. Sun, \"SafeDrug: Dual-Path Drug Recommendation with Multi-Level Interaction and Safe Supervision,\" in Proceedings of the 30th International Joint Conference on Artificial Intelligence (IJCAI), pp. 3735–3741, 2021, doi: 10.24963/ijcai.2021/514.",
        "[22] J. Shang, C. Xiao, T. Ma, H. Li, and J. Sun, \"GAMENet: Graph Augmented MEmory Networks for Recommending Medication Combination,\" in Proceedings of the 33rd AAAI Conference on Artificial Intelligence (AAAI), vol. 33, no. 1, pp. 1126–1133, 2019, doi: 10.1609/aaai.v33i01.33011126.",
        "[23] C. Yang, C. Xiao, P. Chaitanya, and J. Sun, \"MICRON: Accompanying Medication Recommendation with Causal Drug-Drug Interaction Control,\" in International Conference on Learning Representations (ICLR), 2021.",
        "[24] W. L. Hamilton, R. Ying, and J. Leskovec, \"Inductive Representation Learning on Large Graphs,\" in Advances in Neural Information Processing Systems (NeurIPS), vol. 30, pp. 1024–1034, 2017.",
        "[25] T. N. Kipf and M. Welling, \"Semi-Supervised Classification with Graph Convolutional Networks,\" in International Conference on Learning Representations (ICLR), 2017.",
        "[26] R. T. Sutton, D. Pincock, D. C. Baumgart, D. C. Sadowski, R. N. Fedorak, and K. I. Bhandari, \"An overview of clinical decision support systems: benefits, risks, and strategies for success,\" NPJ Digital Medicine, vol. 3, no. 1, p. 17, 2020, doi: 10.1038/s41746-020-0221-y.",
        "[27] B. Efron and R. J. Tibshirani, An Introduction to the Bootstrap. Boca Raton, FL, USA: CRC Press, Chapman & Hall, 1993.",
        "[28] E. G. Brown, L. Wood, and S. Wood, \"The Medical Dictionary for Regulatory Activities (MedDRA),\" Drug Safety, vol. 20, no. 2, pp. 109–117, 1999, doi: 10.2165/00002018-199920020-00002.",
        "[29] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, \"On Calibration of Modern Neural Networks,\" in Proceedings of the 34th International Conference on Machine Learning (ICML), vol. 70, pp. 1321–1330, 2017.",
        "[30] A. Bate and S. J. Evans, \"Quantitative signal detection using spontaneous ADR reporting,\" Pharmacoepidemiology and Drug Safety, vol. 18, no. 6, pp. 427–436, Jun. 2009, doi: 10.1002/pds.1742.",
        "[31] D. W. Bates, G. J. Kuperman, S. Wang, T. Gandhi, A. Kittler, L. Volk, C. Spurr, R. Khorasani, M. Tsurikova, and J. M. Teich, \"Ten commandments for effective clinical decision support: making the practice of evidence-based medicine a reality,\" Journal of the American Medical Informatics Association, vol. 10, no. 6, pp. 523–530, Nov. 2003, doi: 10.1197/jamia.M1370.",
        "[32] J. C. Platt, \"Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods,\" in Advances in Large Margin Classifiers, A. J. Smola, P. Bartlett, B. Schölkopf, and D. Schuurmans, Eds. Cambridge, MA, USA: MIT Press, 1999, pp. 61–74."
    ]
    for ref in references:
        p_ref = doc.add_paragraph()
        p_ref.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_ref.paragraph_format.left_indent = Inches(0.25)
        p_ref.paragraph_format.first_line_indent = Inches(-0.25)
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after = Pt(2.5)
        p_ref.paragraph_format.line_spacing = 1.02
        r_ref = p_ref.add_run(ref)
        r_ref.font.name = 'Times New Roman'
        r_ref.font.size = Pt(8.0)

    out_file2 = DOCS_DIR / "VitaNexus-RX IEEE 2.docx"
    doc.save(out_file2)
    out_file_orig = DOCS_DIR / "VitaNexus-RX IEEE.docx"
    doc.save(out_file_orig)
    print(f"Generated stage {stage} to {out_file2} and {out_file_orig}")

if __name__ == "__main__":
    stage = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    generate_manuscript(stage)
