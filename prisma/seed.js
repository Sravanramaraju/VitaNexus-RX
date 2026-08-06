import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

const medicines = [
  ["Crocin", "Paracetamol (Acetaminophen)"],
  ["Dolo 650", "Paracetamol 650mg"],
  ["Combiflam", "Ibuprofen + Paracetamol"],
  ["Disprin", "Aspirin"],
  ["Digene", "Aluminium Hydroxide + Magnesium Hydroxide + Simethicone"],
  ["Gelusil", "Aluminium Hydroxide + Magnesium Hydroxide + Simethicone"],
  ["ENO", "Sodium Bicarbonate + Citric Acid + Sodium Carbonate"],
  ["Benadryl", "Diphenhydramine"],
  ["Vicks Action 500", "Paracetamol + Phenylephrine + Caffeine"],
  ["Saridon", "Paracetamol + Propyphenazone + Caffeine"],
];

await Promise.all(
  medicines.map(([brand, generic]) =>
    prisma.medicationTerminology.upsert({
      where: { brand_generic: { brand, generic } },
      update: { source: "VitaNexus prototype OTC mapping", version: "2026.08" },
      create: { brand, generic },
    }),
  ),
);

console.log(`Seeded ${medicines.length} medication terminology records.`);
await prisma.$disconnect();
