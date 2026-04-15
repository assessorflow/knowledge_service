# Knowledge Service — Postman gRPC Test Plan (Chemistry)

> **Postman Setup:**
> 1. Open Postman → **New** → **gRPC**
> 2. Server URL: `localhost:9030`
> 3. Click **Service definition** → **Import .proto file** → select: `knowledge-service/proto/assessorflow/knowledge/v1/knowledge.proto`
> 4. Select method from dropdown
> 5. Paste JSON in the **Message** tab (bottom panel)
> 6. Click **Invoke**

---

## Test 1: ProcessMaterial — Document KB (Long Text → Multiple Chunks)

**Method:** `KnowledgeService/ProcessMaterial`

**Message:**
```json
{
    "workflow_id": "wf_chem_001",
    "content_text": "The Periodic Table of Elements is one of the most important tools in chemistry, organizing all known chemical elements by their atomic number, electron configuration, and recurring chemical properties. Dmitri Mendeleev is credited with creating the first widely recognized periodic table in 1869, in which he arranged elements by atomic mass and predicted the existence of elements that had not yet been discovered, such as gallium and germanium.\n\nElements are arranged in rows called periods and columns called groups. Elements within the same group share similar chemical properties because they have the same number of valence electrons. For example, Group 1 elements (lithium, sodium, potassium, rubidium, cesium, and francium) are known as alkali metals. They are highly reactive, especially with water, producing hydrogen gas and a metal hydroxide. Their reactivity increases as you move down the group because the outermost electron is farther from the nucleus and more easily lost. Group 17 elements (fluorine, chlorine, bromine, iodine, and astatine) are called halogens. They are highly reactive nonmetals that readily gain one electron to form negative ions. Fluorine is the most reactive element in the entire periodic table.\n\nChemical bonding is the process by which atoms combine to form molecules and compounds. There are three primary types of chemical bonds: ionic, covalent, and metallic. Ionic bonds form when one atom transfers one or more electrons to another atom, creating oppositely charged ions that attract each other. Sodium chloride (table salt, NaCl) is a classic example — sodium loses one electron to become Na+ and chlorine gains that electron to become Cl-. These ionic compounds typically have high melting points, conduct electricity when dissolved in water, and form crystalline structures.\n\nCovalent bonds form when two atoms share one or more pairs of electrons. This type of bonding typically occurs between nonmetal atoms. Water (H2O) is a well-known covalently bonded molecule — each hydrogen atom shares one electron with the oxygen atom. Covalent bonds can be single (sharing one pair), double (sharing two pairs), or triple (sharing three pairs). Carbon dioxide (CO2) contains two double bonds between carbon and oxygen. The strength of a covalent bond increases with the number of shared electron pairs. Polar covalent bonds occur when electrons are shared unequally between atoms of different electronegativities, creating a partial positive charge on one atom and a partial negative charge on the other. Water is a polar molecule because oxygen is more electronegative than hydrogen.\n\nMetallic bonds are found in metals and alloys, where electrons are delocalized and shared among a lattice of metal cations. This 'sea of electrons' model explains many properties of metals: electrical conductivity (electrons flow freely), thermal conductivity (electrons transfer kinetic energy), malleability (layers of atoms can slide over each other without breaking bonds), and luster (free electrons absorb and re-emit light). Copper, for instance, is an excellent electrical conductor because its delocalized electrons move easily through the metallic lattice.\n\nChemical reactions involve the breaking and forming of chemical bonds, resulting in the transformation of reactants into products. The Law of Conservation of Mass states that matter cannot be created or destroyed in a chemical reaction — the total mass of reactants must equal the total mass of products. Chemical equations must be balanced to reflect this law. For example, the combustion of methane is written as CH4 + 2O2 → CO2 + 2H2O, ensuring equal numbers of each type of atom on both sides.\n\nReaction rates describe how quickly reactants are converted into products. Several factors affect reaction rates: temperature (higher temperature increases molecular kinetic energy and collision frequency), concentration (more reactant particles increase collision probability), surface area (smaller particles expose more surface for reactions), and catalysts (substances that lower the activation energy without being consumed). Enzymes are biological catalysts that dramatically increase reaction rates in living organisms — for example, the enzyme catalase breaks down hydrogen peroxide into water and oxygen approximately 10 million times faster than the uncatalyzed reaction.\n\nAcids and bases are fundamental categories of chemical compounds. According to the Bronsted-Lowry definition, acids are proton (H+) donors and bases are proton acceptors. The pH scale measures the acidity or basicity of a solution, ranging from 0 (strongly acidic) to 14 (strongly basic), with 7 being neutral. Strong acids like hydrochloric acid (HCl) completely dissociate in water, while weak acids like acetic acid (CH3COOH) only partially dissociate. Buffer solutions resist changes in pH when small amounts of acid or base are added — they are critical in biological systems where enzymes function optimally within narrow pH ranges.",
    "source_type": "direct_text",
    "source_file": "chemistry_fundamentals.pdf",
    "assessor_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Expected:** `chunksCreated: 5-8` (long text → multiple chunks), `status: success`

---

## Test 2: ProcessMaterial — Rubric (Policy KB)

**Method:** `KnowledgeService/ProcessMaterial`

**Message:**
```json
{
    "workflow_id": "wf_chem_001",
    "content_text": "For questions about chemical bonding, award full marks if the student correctly identifies the bond type, explains the electron behavior, and provides an appropriate example. Partial marks for correct identification without explanation. For balancing chemical equations, award method marks for showing the correct approach even if the final coefficients are wrong. Deduct marks for confusing ionic and covalent bonds. For acid-base questions, students must use the Bronsted-Lowry definition and reference the pH scale correctly.",
    "source_type": "rubric",
    "source_file": "chemistry_marking_rubric.pdf",
    "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
    "assessment_id": "c3d4e5f6-2222-3333-4444-555566667777"
}
```

**Expected:** `chunksCreated: 1`, `status: success`

---

## Test 3: ProcessMaterial — Web Research (Enriched KB)

**Method:** `KnowledgeService/ProcessMaterial`

**Message:**
```json
{
    "workflow_id": "wf_chem_001",
    "content_text": "Electronegativity is a measure of the tendency of an atom to attract a bonding pair of electrons. The Pauling scale is the most commonly used scale, where fluorine has the highest electronegativity value of 3.98. Electronegativity generally increases across a period from left to right and decreases down a group. The difference in electronegativity between two bonded atoms determines the type of bond: a difference greater than 1.7 typically indicates an ionic bond, while a difference less than 0.4 indicates a nonpolar covalent bond. Values between 0.4 and 1.7 suggest a polar covalent bond.",
    "source_type": "web_research",
    "source_url": "https://www.khanacademy.org/science/chemistry/electronegativity",
    "assessor_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Expected:** `chunksCreated: 1`, `status: success`

---

## Test 4: ProcessMaterial — Duplicate Detection

Send **Test 1 again** with the exact same `workflow_id` and `content_text`.

**Expected:** `chunksCreated: 0`, `status: success` (all chunks deduplicated via content_hash)

---

## Test 5: StoreTopics

**Method:** `KnowledgeService/StoreTopics`

**Message:**
```json
{
    "workflow_id": "wf_chem_001",
    "topics": [
        {
            "name": "General Chemistry",
            "subtopics": [
                {"name": "Periodic Table"},
                {"name": "Chemical Bonding"},
                {"name": "Chemical Reactions"},
                {"name": "Reaction Rates"},
                {"name": "Acids and Bases"},
                {"name": "Electronegativity"}
            ]
        }
    ]
}
```

**Expected:** `status: stored`, `workflowId: wf_chem_001`

---

## Test 6: GetTopics

**Method:** `KnowledgeService/GetTopics`

**Message:**
```json
{
    "workflow_id": "wf_chem_001"
}
```

**Expected:** 1 main topic (General Chemistry) + 6 subtopics

---

## Test 7: SimilaritySearch — Document KB

**Method:** `KnowledgeService/SimilaritySearch`

**Message:**
```json
{
    "query": "What is the difference between ionic and covalent bonds?",
    "workflow_id": "wf_chem_001",
    "kb_type": "document",
    "top_k": 3
}
```

**Expected:** Returns chunks about chemical bonding with `score` > 0

---

## Test 8: SimilaritySearch — Document KB (Different Query)

**Method:** `KnowledgeService/SimilaritySearch`

**Message:**
```json
{
    "query": "How do catalysts affect reaction rates?",
    "workflow_id": "wf_chem_001",
    "kb_type": "document",
    "top_k": 3
}
```

**Expected:** Returns chunks mentioning catalysts, enzymes, activation energy

---

## Test 9: SimilaritySearch — Policy KB

**Method:** `KnowledgeService/SimilaritySearch`

**Message:**
```json
{
    "query": "How to mark chemical bonding questions?",
    "workflow_id": "wf_chem_001",
    "kb_type": "policy",
    "top_k": 3,
    "assessment_id": "c3d4e5f6-2222-3333-4444-555566667777"
}
```

**Expected:** Returns rubric chunks about bonding grading criteria

---

## Test 10: SimilaritySearch — Enriched KB

**Method:** `KnowledgeService/SimilaritySearch`

**Message:**
```json
{
    "query": "What determines whether a bond is ionic or covalent?",
    "workflow_id": "wf_chem_001",
    "kb_type": "enriched",
    "top_k": 3
}
```

**Expected:** Returns web research chunks about electronegativity differences

---

## Test 11: SearchPolicies

**Method:** `KnowledgeService/SearchPolicies`

**Message:**
```json
{
    "query": "method marks for wrong answer",
    "assessment_id": "c3d4e5f6-2222-3333-4444-555566667777",
    "top_k": 5
}
```

**Expected:** Returns rubric chunks about method marks for equations

---

## Test 12: GetChunksByWorkflow

**Method:** `KnowledgeService/GetChunksByWorkflow`

**Message:**
```json
{
    "workflow_id": "wf_chem_001"
}
```

**Expected:** Returns ALL document chunks (5-8 from Test 1)

Save a `chunkId` from the response for Test 13.

---

## Test 13: GetChunksByIds

**Method:** `KnowledgeService/GetChunksByIds`

**Message** (paste chunkId from Test 12):
```json
{
    "chunk_ids": ["<paste_chunkId_here>"]
}
```

**Expected:** Returns that exact chunk

---

## Test Order

| # | Method | What it verifies |
|---|--------|-----------------|
| 1 | ProcessMaterial | Long text → 5-8 chunks in document_chunks |
| 2 | ProcessMaterial | Rubric → policy_chunks with assessment_id |
| 3 | ProcessMaterial | Web research → enriched_chunks with source_url |
| 4 | ProcessMaterial | Duplicate detection (0 new chunks) |
| 5 | StoreTopics | 2-level topic hierarchy (1 main + 6 sub) |
| 6 | GetTopics | Topic tree retrieval |
| 7 | SimilaritySearch | Document KB — bonding query |
| 8 | SimilaritySearch | Document KB — catalysts query |
| 9 | SimilaritySearch | Policy KB — rubric search |
| 10 | SimilaritySearch | Enriched KB — electronegativity |
| 11 | SearchPolicies | Dedicated policy search |
| 12 | GetChunksByWorkflow | Batch retrieve all chunks |
| 13 | GetChunksByIds | Retrieve specific chunk by ID |

---

## Cleanup

```sql
DELETE FROM enriched_chunks WHERE workflow_id = 'wf_chem_001';
DELETE FROM document_chunks WHERE workflow_id = 'wf_chem_001';
DELETE FROM policy_chunks WHERE assessment_id = 'c3d4e5f6-2222-3333-4444-555566667777';
DELETE FROM topics WHERE workflow_id = 'wf_chem_001';
```
