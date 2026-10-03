"""Programmatically curate CNF food selections for KitchenPilot canonical ingredients."""

import csv
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pandas as pd
except ImportError:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file() and Path(sys.executable) != venv_python:
        result = subprocess.run([str(venv_python)] + sys.argv, cwd=str(PROJECT_ROOT))
        sys.exit(result.returncode)
    raise

INGREDIENTS_FILE = PROJECT_ROOT / "data/processed/ingredients.csv"
CNF_FILE = PROJECT_ROOT / "data/processed/cnf_2026_nutrition.csv"
REVIEW_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_review.csv"
VALIDATED_MAPPING_FILE = PROJECT_ROOT / "data/mappings/final_ingredient_mapping_validated.csv"
LINKED_RECIPES_FILE = PROJECT_ROOT / "data/processed/recipe_ingredients_linked.csv"

CURATED_OUTPUT_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_mapping_curated.csv"
REPORT_OUTPUT_FILE = PROJECT_ROOT / "data/mappings/cnf_ingredient_curation_report.csv"

CURATION_SOURCE = "CNF_2026_manual_rule_curation"

# Explicit rule-based curation dictionary for all 128 canonical ingredients.
# Mapping structure:
# ingredient_id: (curation_status, cnf_food_code, curation_reason, match_method, match_score)
CURATION_DECISIONS: dict[str, tuple[str, str, str, str, str]] = {
    # 1. ajwain (default, spice)
    "ING00001": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 2. almond (default, nut)
    "ING00002": ("APPROVED", "2534", "Plain whole unroasted dried almond record selected over roasted nuts, nut butter, and almond meal.", "TOKEN_MATCH", "0.64"),
    # 3. amchur (default, spice)
    "ING00003": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 4. asafoetida (default, spice)
    "ING00004": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 5. baking powder (default, baking)
    "ING00005": ("APPROVED", "4003", "Standard double-acting leavening baking powder record selected.", "TOKEN_MATCH", "0.6786"),
    # 6. baking soda (default, baking)
    "ING00006": ("APPROVED", "4005", "Direct CNF leavening agent match for baking soda.", "TOKEN_MATCH", "0.775"),
    # 7. banana (default, fruit)
    "ING00007": ("APPROVED", "1704", "Direct CNF food identity match with compatible default raw fruit form.", "TOKEN_MATCH", "1.0"),
    # 8. basil (default, herb)
    "ING00008": ("APPROVED", "212", "Fresh culinary herb record selected for default culinary basil.", "TOKEN_MATCH", "0.7"),
    # 9. bay leaf (default, other)
    "ING00009": ("APPROVED", "172", "Direct CNF spice leaf record match for culinary bay leaf.", "TOKEN_MATCH", "0.85"),
    # 10. black pepper (powder, spice)
    "ING00010": ("APPROVED", "198", "Standard black pepper spice record selected for black pepper powder.", "TOKEN_MATCH", "0.85"),
    # 11. black pepper (whole, spice)
    "ING00011": ("APPROVED", "198", "Standard black pepper spice record selected for whole black peppercorns.", "TOKEN_MATCH", "0.85"),
    # 12. brinjal (default, vegetable)
    "ING00012": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 13. broccoli (default, vegetable)
    "ING00013": ("APPROVED", "2374", "Standard raw whole vegetable record selected for default fresh broccoli.", "TOKEN_MATCH", "0.775"),
    # 14. brown sugar (default, sweetener)
    "ING00014": ("APPROVED", "4317", "Candidate set was insufficient (contained only artificial substitutes and pastries); genuine CNF brown sugar record selected.", "CNF_RULE_CURATION", "0.95"),
    # 15. butter (default, dairy)
    "ING00015": ("APPROVED", "118", "Standard commercial regular butter record selected for generic culinary butter.", "TOKEN_MATCH", "0.775"),
    # 16. button mushroom (default, other)
    "ING00016": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 17. cabbage (default, vegetable)
    "ING00017": ("APPROVED", "2361", "Standard raw fresh vegetable record selected over processed kimchi.", "TOKEN_MATCH", "0.775"),
    # 18. cardamom (pod, spice)
    "ING00018": ("NEEDS_REVIEW", "174", "Canonical ingredient specifies whole cardamom pods, but CNF 2026 only provides ground cardamom; requires review to confirm proxying.", "TOKEN_MATCH;FORM_CONFLICT", "0.58"),
    # 19. cardamom (powder, spice)
    "ING00019": ("APPROVED", "174", "Direct ground spice record match for cardamom powder.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 20. carrot (default, vegetable)
    "ING00020": ("APPROVED", "2380", "Standard raw whole vegetable record selected for default fresh carrot.", "TOKEN_MATCH", "0.775"),
    # 21. cashew (default, nut)
    "ING00021": ("APPROVED", "5709", "Standard raw plain cashew nut record selected over nut butter and roasted nuts.", "TOKEN_MATCH", "0.85"),
    # 22. cauliflower (default, vegetable)
    "ING00022": ("APPROVED", "2385", "Standard raw whole vegetable record selected for default fresh cauliflower.", "TOKEN_MATCH", "0.775"),
    # 23. chaat masala (default, spice)
    "ING00023": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 24. chaat masala (powder, spice)
    "ING00024": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 25. chana dal (default, pulse)
    "ING00025": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 26. cheese (default, dairy)
    "ING00026": ("NEEDS_REVIEW", "", "Candidate set contains only specialized cheeses (asiago, blue, brie, etc.) with no defensible generic cheese choice; flagged for review.", "NO_MATCH", "0.0"),
    # 27. chicken (default, meat)
    "ING00027": ("APPROVED", "565", "Candidate review set contained only giblets/feet; standard raw whole broiler chicken meat record selected from CNF.", "CNF_RULE_CURATION", "0.90"),
    # 28. chickpea (kabuli, pulse)
    "ING00028": ("APPROVED", "3389", "Canonical ingredient is whole kabuli chickpea; dry mature seed record selected over boiled, canned, and flour forms.", "TOKEN_MATCH;FORM_MATCH", "0.7025"),
    # 29. cinnamon (powder, spice)
    "ING00029": ("APPROVED", "178", "Direct ground spice record match for cinnamon powder.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 30. cinnamon (stick, spice)
    "ING00030": ("NEEDS_REVIEW", "178", "Canonical ingredient is whole cinnamon stick, but CNF 2026 only provides ground cinnamon; requires review to confirm proxying.", "TOKEN_MATCH;FORM_CONFLICT", "0.58"),
    # 31. cocoa (powder, baking)
    "ING00031": ("APPROVED", "4223", "Candidate review set contained sweetened mocha mix; genuine unsweetened baking cocoa powder record selected from CNF.", "CNF_RULE_CURATION", "0.95"),
    # 32. coconut (default, fruit)
    "ING00032": ("APPROVED", "2558", "Standard raw coconut meat record selected for default fresh coconut.", "TOKEN_MATCH", "0.7"),
    # 33. coconut (desiccated, fruit)
    "ING00033": ("APPROVED", "2559", "Plain unsweetened desiccated coconut meat record selected.", "TOKEN_MATCH;FORM_MATCH", "0.815"),
    # 34. coconut (fresh, fruit)
    "ING00034": ("APPROVED", "2558", "Standard raw fresh coconut meat record selected.", "TOKEN_MATCH", "0.58"),
    # 35. coconut (milk, dairy)
    "ING00035": ("APPROVED", "2565", "Standard culinary canned liquid coconut milk record selected.", "TOKEN_MATCH;FORM_MATCH", "0.69"),
    # 36. coconut oil (default, oil)
    "ING00036": ("APPROVED", "420", "Direct CNF vegetable oil record match for coconut oil.", "TOKEN_MATCH", "0.85"),
    # 37. cooking oil (default, oil)
    "ING00037": ("APPROVED", "451", "Standard neutral commercial cooking vegetable oil (canola) record selected from candidate set.", "TOKEN_MATCH", "0.7"),
    # 38. coriander (leaf, herb)
    "ING00038": ("APPROVED", "2067", "Raw fresh cilantro/coriander leaf record selected for fresh culinary coriander leaves.", "TOKEN_MATCH", "0.58"),
    # 39. coriander (powder, spice)
    "ING00039": ("NEEDS_REVIEW", "181", "Canonical ingredient is coriander powder, but CNF 2026 lacks a ground coriander powder record; seed record flagged for review.", "TOKEN_MATCH;FORM_CONFLICT", "0.5425"),
    # 40. coriander (seed, spice)
    "ING00040": ("APPROVED", "181", "Direct seed spice record match for coriander seeds.", "TOKEN_MATCH;FORM_MATCH", "0.815"),
    # 41. corn (flour, flour)
    "ING00041": ("APPROVED", "4417", "Standard yellow whole grain corn flour record selected.", "TOKEN_MATCH;FORM_MATCH", "0.77"),
    # 42. cream (fresh, dairy)
    "ING00042": ("APPROVED", "136", "Standard fluid table/cooking sweet cream (18% M.F.) selected over cultured sour cream.", "TOKEN_MATCH", "0.625"),
    # 43. cucumber (default, vegetable)
    "ING00043": ("APPROVED", "2363", "Standard raw whole vegetable record selected for default cucumber.", "TOKEN_MATCH", "0.775"),
    # 44. cumin (default, spice)
    "ING00044": ("APPROVED", "182", "Direct spice seed record match for default culinary cumin.", "TOKEN_MATCH", "0.7"),
    # 45. cumin (powder, spice)
    "ING00045": ("NEEDS_REVIEW", "182", "Canonical ingredient specifies cumin powder, but CNF 2026 only contains cumin seed; requires review to confirm proxying.", "TOKEN_MATCH;FORM_CONFLICT", "0.58"),
    # 46. cumin (seed, spice)
    "ING00046": ("APPROVED", "182", "Direct spice seed record match for cumin seeds.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 47. curd (default, dairy)
    "ING00047": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 48. curd (hung, dairy)
    "ING00048": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 49. curry leaf (default, herb)
    "ING00049": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 50. date (default, fruit)
    "ING00050": ("APPROVED", "1710", "Standard domestic natural dry date record selected for generic dates.", "TOKEN_MATCH", "0.64"),
    # 51. dry red chilli (default, other)
    "ING00051": ("APPROVED", "2355", "Candidate review set contained an invalid pulse match; genuine sun-dried red chili record selected from CNF.", "CNF_RULE_CURATION", "0.90"),
    # 52. egg (default, egg)
    "ING00052": ("APPROVED", "125", "Standard raw whole chicken egg record selected over composite egg dishes.", "CNF_RULE_CURATION", "0.95"),
    # 53. fennel (default, spice)
    "ING00053": ("APPROVED", "186", "Culinary spice seed record selected for default culinary fennel.", "TOKEN_MATCH", "0.7"),
    # 54. fennel (seed, spice)
    "ING00054": ("APPROVED", "186", "Direct spice seed record match for fennel seeds.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 55. fenugreek (seed, spice)
    "ING00055": ("APPROVED", "187", "Direct spice seed record match for fenugreek seeds.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 56. fenugreek leaves (default, herb)
    "ING00056": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 57. fenugreek leaves (fresh, herb)
    "ING00057": ("NO_MATCH", "", "Candidate review file suggested unrelated amaranth leaves; CNF 2026 lacks fenugreek leaves, retained as NO_MATCH.", "NO_MATCH", "0.0"),
    # 58. garam masala (powder, spice)
    "ING00058": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 59. garlic (default, vegetable)
    "ING00059": ("APPROVED", "2394", "Standard raw whole vegetable record selected over garlic powder.", "TOKEN_MATCH", "0.775"),
    # 60. ghee (default, dairy)
    "ING00060": ("APPROVED", "7829", "Direct CNF clarified butter (ghee) record match.", "ALIAS_MATCH", "0.96"),
    # 61. ginger (default, root)
    "ING00061": ("APPROVED", "2091", "Standard raw root vegetable record selected over ground ginger and pickled ginger.", "TOKEN_MATCH", "0.7"),
    # 62. ginger garlic (paste, paste)
    "ING00062": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 63. green beans (default, vegetable)
    "ING00063": ("APPROVED", "2370", "Candidate review file offered winged beans; genuine raw snap green bean record selected from CNF.", "CNF_RULE_CURATION", "0.90"),
    # 64. green bell pepper (default, vegetable)
    "ING00064": ("APPROVED", "2413", "Standard raw whole sweet green pepper record selected.", "TOKEN_MATCH", "0.5467"),
    # 65. green chilli (default, other)
    "ING00065": ("APPROVED", "2322", "Standard raw fresh hot green chili record selected over canned chili.", "TOKEN_MATCH", "0.6786"),
    # 66. green peas (fresh, vegetable)
    "ING00066": ("APPROVED", "2409", "Standard fresh raw green pea record selected over boiled and canned peas.", "TOKEN_MATCH;FORM_CONFLICT", "0.73"),
    # 67. honey (default, sweetener)
    "ING00067": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 68. jaggery (default, sweetener)
    "ING00068": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 69. kashmiri red chilli (powder, spice)
    "ING00069": ("NEEDS_REVIEW", "177", "Kashmiri red chilli is a mild red chili powder; mapped to generic chili powder pending review of spice potency.", "TOKEN_MATCH;FORM_CONFLICT", "0.3592"),
    # 70. lemon (default, fruit)
    "ING00070": ("APPROVED", "1587", "Standard raw whole fruit record selected over peel, juice, and composite dishes.", "TOKEN_MATCH", "0.6625"),
    # 71. lemon juice (default, fruit)
    "ING00071": ("APPROVED", "1589", "Standard fresh raw lemon juice record selected over canned and frozen juice.", "TOKEN_MATCH", "0.85"),
    # 72. mango (default, fruit)
    "ING00072": ("APPROVED", "1603", "Direct CNF raw fruit match for fresh mango.", "TOKEN_MATCH", "1.0"),
    # 73. milk (default, dairy)
    "ING00073": ("NEEDS_REVIEW", "61", "Generic milk requires decision between standard whole fluid milk and partly skimmed 2% milk from candidate set; flagged for review.", "TOKEN_MATCH", "0.6143"),
    # 74. mint leaf (default, herb)
    "ING00074": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 75. moong dal (default, pulse)
    "ING00075": ("APPROVED", "3297", "Dry mature mung seed record selected over boiled seeds and bean sprouts.", "TOKEN_MATCH", "1.0"),
    # 76. mozzarella (default, dairy)
    "ING00076": ("APPROVED", "110", "Standard commercial mozzarella cheese record (25% M.F.) selected.", "TOKEN_MATCH", "0.7"),
    # 77. mustard (default, spice)
    "ING00077": ("APPROVED", "192", "Mustard spice seed record selected over leafy mustard green vegetable records.", "TOKEN_MATCH", "0.6625"),
    # 78. mustard (oil, oil)
    "ING00078": ("APPROVED", "452", "Direct vegetable oil record match for mustard oil.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 79. mustard (seed, spice)
    "ING00079": ("APPROVED", "192", "Direct spice seed record match for mustard seeds.", "TOKEN_MATCH;FORM_MATCH", "0.815"),
    # 80. mutton (default, meat)
    "ING00080": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 81. oats (default, other)
    "ING00081": ("APPROVED", "4421", "Standard dry whole oats grain record selected.", "TOKEN_MATCH", "0.7"),
    # 82. olive oil (default, oil)
    "ING00082": ("APPROVED", "422", "Direct vegetable oil record match for 100% pure olive oil.", "TOKEN_MATCH", "0.85"),
    # 83. onion (default, vegetable)
    "ING00083": ("APPROVED", "2401", "Standard raw whole vegetable record selected for default fresh onion.", "TOKEN_MATCH", "0.775"),
    # 84. oregano (default, herb)
    "ING00084": ("APPROVED", "195", "Standard dried culinary oregano spice record selected.", "TOKEN_MATCH", "0.7"),
    # 85. paneer (default, dairy)
    "ING00085": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 86. paprika (powder, spice)
    "ING00086": ("APPROVED", "196", "Direct spice record match for paprika powder.", "TOKEN_MATCH", "0.775"),
    # 87. parmesan (default, dairy)
    "ING00087": ("APPROVED", "40", "Standard hard block parmesan cheese record selected.", "TOKEN_MATCH", "0.85"),
    # 88. parsley (default, herb)
    "ING00088": ("APPROVED", "2405", "Fresh culinary herb record selected for default fresh parsley.", "TOKEN_MATCH", "0.775"),
    # 89. peanut (default, nut)
    "ING00089": ("APPROVED", "3396", "Standard generic raw peanut record selected over specific cultivars, roasted nuts, and peanut butter.", "TOKEN_MATCH", "0.775"),
    # 90. pistachio (default, nut)
    "ING00090": ("APPROVED", "2644", "Standard raw plain pistachio nut record selected over roasted nuts.", "TOKEN_MATCH", "0.7"),
    # 91. poppy (seed, seed)
    "ING00091": ("APPROVED", "201", "Direct spice seed record match for poppy seeds.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 92. potato (default, vegetable)
    "ING00092": ("APPROVED", "2505", "Canonical ingredient is default form vegetable; raw potato record selected over boiled/prepared candidate rows.", "CNF_RULE_CURATION", "0.95"),
    # 93. pumpkin (default, vegetable)
    "ING00093": ("APPROVED", "2441", "Standard raw whole vegetable record selected over boiled pumpkin and pumpkin flowers.", "TOKEN_MATCH", "0.775"),
    # 94. raisin (default, dried fruit)
    "ING00094": ("APPROVED", "1745", "Standard seedless brown raisin (sultana / kishmish) record selected.", "ALIAS_MATCH", "0.96"),
    # 95. red bell pepper (default, vegetable)
    "ING00095": ("APPROVED", "2484", "Standard raw whole sweet red pepper record selected.", "TOKEN_MATCH", "0.5467"),
    # 96. red chilli (dried, spice)
    "ING00096": ("APPROVED", "2355", "Canonical ingredient is dry red chili; genuine sun-dried red chili record selected over invalid pulse match.", "CNF_RULE_CURATION", "0.90"),
    # 97. red chilli (flakes, spice)
    "ING00097": ("NEEDS_REVIEW", "2355", "Canonical ingredient is red chili flakes; mapped to sun-dried whole red chili pending review of flake preparation form.", "TOKEN_MATCH;FORM_CONFLICT", "0.58"),
    # 98. red chilli (powder, spice)
    "ING00098": ("APPROVED", "177", "Standard chili powder spice record selected for red chili powder.", "TOKEN_MATCH;FORM_MATCH", "0.6317"),
    # 99. rice (basmati, grain)
    "ING00099": ("APPROVED", "4471", "Standard dry white long-grain rice record selected to represent dry Basmati long-grain rice.", "TOKEN_MATCH;FORM_CONFLICT", "0.505"),
    # 100. rice (default, grain)
    "ING00100": ("APPROVED", "4471", "Standard dry regular long-grain white rice record selected for default culinary rice.", "TOKEN_MATCH", "0.625"),
    # 101. rice (flour, flour)
    "ING00101": ("APPROVED", "4429", "Standard white rice flour record selected for culinary rice flour.", "TOKEN_MATCH;FORM_MATCH", "0.815"),
    # 102. saffron (strand, spice)
    "ING00102": ("APPROVED", "205", "Direct culinary spice record match for saffron strands.", "TOKEN_MATCH", "0.775"),
    # 103. salt (default, seasoning)
    "ING00103": ("APPROVED", "214", "Direct table salt seasoning record match.", "TOKEN_MATCH", "0.775"),
    # 104. sambar powder (default, spice)
    "ING00104": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 105. semolina (default, grain)
    "ING00105": ("APPROVED", "4478", "Direct grain record match for semolina (sooji/rava).", "TOKEN_MATCH", "0.775"),
    # 106. sesame (oil, oil)
    "ING00106": ("APPROVED", "424", "Direct vegetable oil record match for sesame oil.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 107. sesame (seed, seed)
    "ING00107": ("APPROVED", "2521", "Whole sesame seeds record selected for culinary sesame seeds.", "TOKEN_MATCH;FORM_MATCH", "0.74"),
    # 108. soy sauce (default, condiment)
    "ING00108": ("APPROVED", "3403", "Standard regular brewed soy sauce (shoyu) record selected.", "TOKEN_MATCH", "0.6625"),
    # 109. spinach (default, vegetable)
    "ING00109": ("APPROVED", "2213", "Standard raw fresh vegetable record selected for default fresh spinach.", "TOKEN_MATCH", "0.775"),
    # 110. star anise (default, spice)
    "ING00110": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 111. sugar (caster, sweetener)
    "ING00111": ("APPROVED", "4318", "Candidate review file suggested sugar-apple fruit; genuine white refined sugar record selected for caster sugar.", "CNF_RULE_CURATION", "0.95"),
    # 112. sugar (default, sweetener)
    "ING00112": ("APPROVED", "4318", "Candidate review file suggested sugar-apple fruit; genuine white granulated sugar record selected for table sugar.", "CNF_RULE_CURATION", "0.95"),
    # 113. sunflower oil (default, oil)
    "ING00113": ("APPROVED", "7191", "Standard refined mid-oleic cooking vegetable oil record selected for sunflower oil.", "TOKEN_MATCH", "0.73"),
    # 114. sweet corn (default, other)
    "ING00114": ("APPROVED", "2388", "Standard raw fresh yellow sweet corn record selected.", "TOKEN_MATCH", "0.775"),
    # 115. tamarind (default, condiment)
    "ING00115": ("APPROVED", "1689", "Direct raw fruit/pulp record match for default tamarind.", "TOKEN_MATCH", "0.775"),
    # 116. tamarind (paste, condiment)
    "ING00116": ("NEEDS_REVIEW", "1689", "Canonical ingredient is tamarind paste, but CNF 2026 only provides raw tamarind; requires review to confirm proxying.", "TOKEN_MATCH;FORM_CONFLICT", "0.655"),
    # 117. tofu (default, soy)
    "ING00117": ("APPROVED", "4913", "Plain firm refrigerated tofu record selected over fried and composite tofu dishes.", "TOKEN_MATCH", "0.6625"),
    # 118. tomato (default, vegetable)
    "ING00118": ("APPROVED", "2460", "Standard raw fresh tomato record selected over boiled and canned tomato forms.", "TOKEN_MATCH", "0.6625"),
    # 119. tomato (puree, vegetable)
    "ING00119": ("APPROVED", "6580", "Direct canned tomato puree product match for tomato puree.", "TOKEN_MATCH;FORM_MATCH", "0.815"),
    # 120. toor dal (default, pulse)
    "ING00120": ("APPROVED", "3312", "Validated alias maps to pigeon peas; dry mature-seed form selected over boiled records.", "ALIAS_MATCH", "0.96"),
    # 121. turmeric (powder, spice)
    "ING00121": ("APPROVED", "211", "Direct ground spice record match for turmeric powder.", "TOKEN_MATCH;FORM_MATCH", "0.89"),
    # 122. urad dal (white, pulse)
    "ING00122": ("NO_MATCH", "", "No suitable CNF 2026 record found; retained as NO_MATCH rather than forcing an unrelated food.", "NO_MATCH", "0.0"),
    # 123. vanilla (default, flavoring)
    "ING00123": ("APPROVED", "216", "Direct culinary vanilla extract record match.", "ALIAS_MATCH", "0.97"),
    # 124. vinegar (default, condiment)
    "ING00124": ("APPROVED", "14", "Standard plain distilled white vinegar record selected for generic culinary vinegar.", "TOKEN_MATCH", "0.7"),
    # 125. walnut (default, nut)
    "ING00125": ("APPROVED", "2590", "Standard unglazed English/Persian walnut record selected over glazed and roasted walnuts.", "TOKEN_MATCH", "0.64"),
    # 126. water (default, liquid)
    "ING00126": ("APPROVED", "2933", "Standard municipal tap water liquid record selected.", "TOKEN_MATCH", "0.775"),
    # 127. yeast (active dry, baking)
    "ING00127": ("APPROVED", "4008", "Genuine active dry baker's yeast leavening record selected over yeast extract spread.", "CNF_RULE_CURATION", "0.95"),
    # 128. yellow bell pepper (default, vegetable)
    "ING00128": ("APPROVED", "2344", "Direct raw fresh sweet yellow pepper record match.", "TOKEN_MATCH", "0.5467"),
}


def build_curated_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the curated mapping and report dataframes."""
    ings_df = pd.read_csv(INGREDIENTS_FILE, dtype=str).fillna("")
    rev_df = pd.read_csv(REVIEW_FILE, dtype=str).fillna("")
    cnf_df = pd.read_csv(CNF_FILE, dtype=str).fillna("").drop_duplicates("source_food_id")
    cnf_by_id = cnf_df.set_index("source_food_id").to_dict("index")

    rev_grouped: dict[str, pd.DataFrame] = {}
    for ing_id, group in rev_df.groupby("ingredient_id"):
        rev_grouped[ing_id] = group

    curated_rows = []
    report_rows = []

    for _, ing_row in ings_df.iterrows():
        ing_id = ing_row["ingredient_id"]
        cname = ing_row["canonical_name"]
        dname = ing_row["display_name"]
        iform = ing_row["ingredient_form"]
        cat = ing_row["category"]

        group = rev_grouped.get(ing_id)
        cand_count = (
            len(group)
            if group is not None and group.iloc[0]["selection_status"] != "NO_MATCH"
            else 0
        )
        top_cand_str = ""
        if group is not None and cand_count > 0:
            top_cand = group.iloc[0]
            top_cand_str = f"[{top_cand['cnf_food_code']}] {top_cand['cnf_food_name']}"

        recipe_evidence = group.iloc[0]["recipe_form_evidence"] if group is not None else ""
        review_notes = group.iloc[0]["review_notes"] if group is not None else ""

        if ing_id not in CURATION_DECISIONS:
            raise ValueError(f"Missing curation decision for ingredient: {ing_id}")

        status, code, reason, method, score = CURATION_DECISIONS[ing_id]

        if code and code in cnf_by_id:
            cnf_item = cnf_by_id[code]
            food_name = cnf_item["food_name"]
            food_desc = cnf_item["food_description"]
            # Preserve cnf_food_form from review file if candidate exists, else cnf record
            cand_match = group[group["cnf_food_code"] == code] if group is not None else None
            if cand_match is not None and len(cand_match) > 0:
                food_form = cand_match.iloc[0]["cnf_food_form"]
            else:
                food_form = cnf_item["food_form"]
            sel_cand_str = f"[{code}] {food_name}"
        else:
            food_name = ""
            food_desc = ""
            food_form = ""
            sel_cand_str = ""

        curated_rows.append({
            "ingredient_id": ing_id,
            "canonical_name": cname,
            "display_name": dname,
            "ingredient_form": iform,
            "category": cat,
            "cnf_food_code": code,
            "cnf_food_name": food_name,
            "cnf_food_form": food_form,
            "cnf_food_description": food_desc,
            "match_method": method,
            "match_score": score,
            "curation_status": status,
            "curation_reason": reason,
            "curation_source": CURATION_SOURCE,
            "recipe_form_evidence": recipe_evidence,
            "review_notes": review_notes,
        })

        report_rows.append({
            "ingredient_id": ing_id,
            "canonical_name": cname,
            "ingredient_form": iform,
            "top_candidate": top_cand_str,
            "selected_candidate": sel_cand_str,
            "curation_status": status,
            "curation_reason": reason,
            "candidate_count": cand_count,
        })

    curated_df = pd.DataFrame(curated_rows)
    report_df = pd.DataFrame(report_rows)
    return curated_df, report_df


def save_tables(curated_df: pd.DataFrame, report_df: pd.DataFrame) -> None:
    """Save the curated and report CSV tables."""
    CURATED_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    curated_df.to_csv(CURATED_OUTPUT_FILE, index=False, encoding="utf-8-sig")
    report_df.to_csv(REPORT_OUTPUT_FILE, index=False, encoding="utf-8-sig")


def print_summary(curated_df: pd.DataFrame) -> None:
    """Print standard completion summary and key ingredient decisions."""
    total = len(curated_df)
    approved = int((curated_df["curation_status"] == "APPROVED").sum())
    no_match = int((curated_df["curation_status"] == "NO_MATCH").sum())
    needs_review = int((curated_df["curation_status"] == "NEEDS_REVIEW").sum())

    print("==================================================")
    print("CNF CURATION COMPLETE")
    print("==================================================")
    print(f"\nCanonical ingredients: {total}")
    print(f"APPROVED: {approved}")
    print(f"NO_MATCH: {no_match}")
    print(f"NEEDS_REVIEW: {needs_review}")
    print(f"\nOutput:\n{CURATED_OUTPUT_FILE}")
    print(f"\nReport:\n{REPORT_OUTPUT_FILE}")

    print("\n==================================================")
    print("IMPORTANT INGREDIENT DECISIONS")
    print("==================================================")

    # 15 important ingredients to report
    important_canonical_names = [
        "rice", "toor dal", "moong dal", "chickpea", "turmeric",
        "cumin", "onion", "tomato", "ginger", "garlic",
        "ghee", "milk", "almond", "banana"
    ]

    for _, row in curated_df.iterrows():
        cname = row["canonical_name"]
        if cname in important_canonical_names:
            print(f"\ncanonical ingredient: {cname} ({row['display_name']}, form: {row['ingredient_form']})")
            print(f"selected CNF food code: {row['cnf_food_code']}")
            print(f"selected CNF food name: {row['cnf_food_name']}")
            print(f"CNF form: {row['cnf_food_form']}")
            print(f"curation status: {row['curation_status']}")
            print(f"reason: {row['curation_reason']}")

    # Explicit note regarding chickpea flour
    print("\ncanonical ingredient: chickpea flour")
    print("selected CNF food code: N/A")
    print("selected CNF food name: N/A")
    print("CNF form: N/A")
    print("curation status: NOT_IN_CANONICAL_TABLE")
    print("reason: Canonical ingredients table defines whole chickpea ING00028 (which maps to dry mature chickpeas [3389]); chickpea flour (besan) is not an independent canonical ingredient in ingredients.csv.")


def main() -> None:
    curated_df, report_df = build_curated_tables()
    save_tables(curated_df, report_df)
    print_summary(curated_df)


if __name__ == "__main__":
    main()
