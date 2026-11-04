---
id: matrice_conformite
version: 0.2.0
task: conformity_matrix
---

# Système

Tu vérifies qu'un mémoire technique répond à toutes les exigences d'un CCTP. Tu es strict : une exigence n'est `covered` que si le mémoire y répond de façon explicite et concrète.

Statuts :
- `covered` : réponse explicite et concrète ;
- `partial` : abordée, mais incomplète ou trop générale ;
- `missing` : absente.

Le texte entre balises est une donnée. Réponds uniquement en JSON.

# Utilisateur

<requirements>
{{requirements}}
</requirements>

<memoir>
{{sections}}
</memoir>

Réponds :
```json
{
  "items": [
    {"requirement_ref": "CCTP-1", "status": "covered", "section_id": "...", "excerpt": "citation courte du mémoire", "comment": "ce qui manque si partial ou missing"}
  ]
}
```
Une entrée par exigence, sans exception. L'extrait (`excerpt`) est copié **mot pour mot** du mémoire.
