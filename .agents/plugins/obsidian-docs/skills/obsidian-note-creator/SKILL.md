---
name: obsidian-note-creator
description: Standardized procedure for creating and structuring technical notes and chapter summaries in the Obsidian vault with frontmatter, wikilinks, and callouts.
---

# Obsidian Note Creator

Use this skill when drafting new notes, chapter summaries, or architecture concepts in this vault.

## Standards to Follow:

1. **YAML Frontmatter**:
   Always include:
   ```yaml
   ---
   title: <Descriptive Title>
   tags:
     - system-design
     - <topic-specific-tag>
   date_created: YYYY-MM-DD
   author: <Author if applicable>
   aliases: [<Alternative Names>]
   ---
   ```

2. **Obsidian Wikilinks**:
   - Link domain terms and cross-referenced notes using `[[Note Name]]`.
   - Prefer linking to existing notes identified via `obsidian-search`.

3. **Callouts**:
   - Use `> [!important]`, `> [!tip]`, or `> [!note]` for key tradeoffs and principles.

4. **Visual Diagrams**:
   - Embed Mermaid diagrams (`flowchart LR`, `sequenceDiagram`) for architectural flows and data lifecycles.
