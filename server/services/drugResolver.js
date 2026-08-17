import { normalizeClinicalTerm } from "../repositories/clinicalKnowledgeRepository.js";

export const resolveDrug = async (client, { enteredName, brand, genericName }) => {
  const suppliedName = (enteredName || brand || genericName || "").trim();
  const normalizedName = normalizeClinicalTerm(suppliedName);
  let mapping = normalizedName
    ? await client.medicationTerminology.findFirst({
        where: {
          OR: [
            { normalizedBrand: normalizedName },
            { normalizedGeneric: normalizedName },
          ],
        },
        orderBy: { createdAt: "desc" },
      })
    : null;
  if (!mapping && normalizedName) {
    mapping = await client.medicationTerminology.findFirst({
      where: { OR: [{ normalizedBrand: { contains: normalizedName } }, { normalizedGeneric: { contains: normalizedName } }] },
      orderBy: { createdAt: "desc" },
    });
  }

  return {
    enteredName: suppliedName || null,
    normalizedName,
    brand: mapping?.brand || brand || null,
    genericName: mapping?.generic || genericName || suppliedName,
    mappingSource: mapping?.source || null,
    mappingVersion: mapping?.version || null,
  };
};
