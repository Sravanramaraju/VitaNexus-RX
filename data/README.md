# Clinical knowledge datasets

Raw downloads are kept outside application patient data and must not be edited. Run `npm run data:process` to produce repeatable processed NDJSON artifacts, then run `npm run data:import` after the Prisma migration has been deployed.

- `raw/ddinter/` supplies DDInter 2.0 interaction classifications.
- `raw/durgcentral/` contains the downloaded DrugCentral PostgreSQL dump (version is taken from the download filename). DrugCentral extraction is intentionally a separate, reviewable import stage before drug-disease and indication rows are loaded.
- `raw/indian medicne/` supplies terminology-only brand/product-to-generic mappings.
- `raw/FDA ADR Reports/` supplies quarterly FAERS ASCII archives for the separate temporal ML pipeline. Use the `npm run ml:*` commands documented in the root README; these files are never loaded into the clinical knowledge tables.

Processed knowledge is never patient data. The loader retains a source and version/date on every imported relationship.
