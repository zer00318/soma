# Scene Eval Summary

- N: 37
- Correct: 37/37 = 100.0% (95% Wilson CI: 90.6% to 100.0%)
- Hallucination: 0/37 = 0.0% (95% Wilson CI: 0.0% to 9.4%)
- Wrong: 0

| idx | moment | expect | verdict | refused | question | answer |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pantry | answer | correct | False | is there a water bottle | Yes, I saw a water bottle. (seen at 1.0s) |
| 2 | pantry | answer | correct | False | how many water bottles | I saw at least 1 water bottle, but I can't reliably count it yet. (seen at 1.0s) |
| 3 | pantry | answer | correct | False | what colour is the water bottle | The water bottle is blue. (seen at 1.0s) |
| 4 | pantry | answer | correct | False | what flavour is the pringles | The pringle is sour cream and onion. (seen at 2.0s) About what you saw (general knowledge, not from your memory): • pringles can: Pringles is a brand of stackable potato crisps. |
| 5 | pantry | answer | correct | False | is there a pringles can | Yes, I saw a pringle can. (seen at 2.0s) About what you saw (general knowledge, not from your memory): • pringles can: Pringles is a brand of stackable potato crisps. |
| 6 | pantry | answer | correct | False | what label is on the cereal box | The cereal box is morning oats. (seen at 3.0s) |
| 7 | pantry | answer | correct | False | is there a cereal box | Yes, I saw a cereal box. (seen at 3.0s) |
| 8 | pantry | answer | correct | False | what label is on the soda can | The soda can is club soda. (seen at 5.0s) |
| 9 | pantry | refuse | correct | True | is there pesto | I don't have that in my memory — I didn't read enough to be sure. |
| 10 | pantry | refuse | correct | True | how many nutella jars | I don't have that in my memory — I didn't read enough to be sure. |
| 11 | pantry | refuse | correct | True | is there nutella | I don't have that in my memory — I didn't read enough to be sure. |
| 12 | desk | answer | correct | False | is there a coffee mug | Yes, I saw a coffee mug. (seen at 1.0s) |
| 13 | desk | answer | correct | False | how many coffee mugs | I saw at least 2 coffee mugs, but I can't reliably count them yet. (seen at 1.0s, 3.0s) |
| 14 | desk | answer | correct | False | what colour is the notebook | The notebook is green. (seen at 2.0s) |
| 15 | desk | answer | correct | False | is there a notebook | Yes, I saw a notebook. (seen at 2.0s) |
| 16 | desk | answer | correct | False | what label is on the tea tin | The tea tin is earl grey. (seen at 4.0s) |
| 17 | desk | answer | correct | False | is there a tea tin | Yes, I saw a tea tin. (seen at 4.0s) |
| 18 | desk | answer | correct | False | what colour is the pen cup | The pen cup is black. (seen at 5.0s) |
| 19 | desk | refuse | correct | True | how many rings | I don't have that in my memory — I didn't read enough to be sure. |
| 20 | fridge | answer | correct | False | how many water bottles | I saw 2 water bottles. (seen at 1.0s, 1.4s, 2.0s, 2.4s) |
| 21 | fridge | answer | correct | False | is there a water bottle | Yes, I saw a water bottle. (seen at 1.0s) |
| 22 | fridge | answer | correct | False | what colour is the juice carton | The juice carton is orange. (seen at 4.0s) |
| 23 | fridge | answer | correct | False | what label is on the juice carton | The juice carton is sunvale orange. (seen at 4.0s) |
| 24 | fridge | answer | correct | False | is there a yogurt cup | Yes, I saw a yogurt cup. (seen at 3.0s) |
| 25 | fridge | answer | correct | False | how many yogurt cups | I saw at least 1 yogurt cup, but I can't reliably count it yet. (seen at 3.0s) |
| 26 | fridge | answer | correct | False | is there a juice carton | Yes, I saw a juice carton. (seen at 4.0s) |
| 27 | fridge | answer | correct | False | how many juice cartons | I saw at least 1 juice carton, but I can't reliably count it yet. (seen at 4.0s) |
| 28 | fridge | refuse | correct | True | is there a tortilla | I don't have that in my memory — I didn't read enough to be sure. |
| 29 | sideboard | answer | correct | False | how many candle jars | I saw 2 candle jars. (seen at 1.0s, 1.6s, 2.4s) |
| 30 | sideboard | answer | correct | False | is there a candle jar | Yes, I saw a candle jar. (seen at 1.0s) |
| 31 | sideboard | answer | correct | False | what colour is the candle jar | The candle jar is blue. (seen at 1.0s) |
| 32 | sideboard | answer | correct | False | what label is on the book | The book is city walks. (seen at 3.0s) |
| 33 | sideboard | answer | correct | False | is there a cracker box | Yes, I saw a cracker box. (seen at 4.0s) |
| 34 | sideboard | answer | correct | False | what flavour is the cracker box | The cracker box is rosemary. (seen at 4.0s) |
| 35 | sideboard | answer | correct | False | is there an apple | Yes, I saw an apple. (seen at 5.0s) |
| 36 | sideboard | answer | correct | False | what colour is the apple | The apple is red. (seen at 5.0s) |
| 37 | sideboard | answer | correct | False | how many apples | I saw at least 1 apple, but I can't reliably count it yet. (seen at 5.0s) |
