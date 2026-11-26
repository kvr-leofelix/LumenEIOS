"""Curriculum content for the demonstration schools: NCERT chapters (2024-25 / 2025-26 textbooks) and a
teacher-written question bank, one question per competency per chapter.

Chapters are listed in teaching order. `taught_by` is the month (1-12) by which the chapter has normally been
completed in an April-March CBSE session; exams only use chapters taught before the exam date.

Question tuple: (competency, type, text, options, answer, rubric, marks, bloom)
  competency: LU Language Understanding · CU Conceptual Understanding · AU Application · CT Critical Thinking
"""
from typing import Dict, List, Tuple

Q = Tuple[str, str, str, List[str], str, str, int, str]

SUBJECT_BOOKS = {
    "sub-math": "Ganita Prakash", "sub-sci": "Curiosity", "sub-eng": "Poorvi",
    "sub-sst": "Exploring Society: India and Beyond", "sub-hin": "मल्हार",
}

CONTENT: Dict[Tuple[int, str], List[dict]] = {
    # ------------------------------------------------------------------ Mathematics
    (6, "sub-math"): [
        {"title": "Patterns in Mathematics", "taught_by": 4, "questions": [
            ("LU", "mcq", "Which of these is the sequence of triangular numbers?", ["1, 3, 6, 10, 15", "1, 4, 9, 16, 25", "1, 2, 4, 8, 16", "2, 4, 6, 8, 10"], "1, 3, 6, 10, 15", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Explain why adding consecutive odd numbers starting from 1 always gives a square number. Use 1 + 3 + 5 + 7 as an example.", [], "1 + 3 + 5 + 7 = 16 = 4 × 4; each new odd number adds one row and one column to the previous square, so the dots always form a square.", "1 mark for the sum 16; 1 mark for the square-growth explanation.", 2, "Understand"),
            ("AU", "short", "Write the next two terms of the pattern 2, 6, 12, 20, 30, … and state the rule.", [], "42, 56. Differences are 4, 6, 8, 10, so the next differences are 12 and 14.", "1 mark per correct term; 1 mark for the rule.", 3, "Apply"),
            ("CT", "short", "Riya says 1, 2, 4, 8 must continue as 16. Arjun says it could continue as 15. Who is right? Justify.", [], "Both can be right: doubling gives 16, while adding 1, 2, 4, 7 (differences increasing by 1, 2, 3) gives 15. A few terms do not fix a unique rule.", "1 mark for recognising both rules; 1 mark for the justification.", 2, "Evaluate"),
        ]},
        {"title": "Lines and Angles", "taught_by": 5, "questions": [
            ("LU", "mcq", "An angle that measures exactly 90° is called a", ["right angle", "acute angle", "obtuse angle", "straight angle"], "right angle", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What is the difference between a line segment and a ray?", [], "A line segment has two end points and a fixed length; a ray has one end point and extends without end in one direction.", "1 mark for each correct description.", 2, "Understand"),
            ("AU", "short", "The hands of a clock show 3 o'clock. What angle do they make? What angle at 6 o'clock?", [], "90° at 3 o'clock; 180° (a straight angle) at 6 o'clock.", "1 mark for each angle.", 2, "Apply"),
            ("CT", "short", "Meena says an angle of 200° is impossible. Do you agree? Explain with a drawing description.", [], "Disagree: a reflex angle can be more than 180° and less than 360°; turning the arm past the straight line gives 200°.", "1 mark for disagreeing; 1 mark for the reflex-angle reason.", 2, "Evaluate"),
        ]},
        {"title": "Number Play", "taught_by": 7, "questions": [
            ("LU", "mcq", "A number that reads the same forwards and backwards, like 1331, is called a", ["palindrome", "prime", "multiple", "factor"], "palindrome", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why is the sum of two odd numbers always even?", [], "Each odd number is one more than an even number; the two extra 1s make 2, so the total is even.", "2 marks for a correct general reason.", 2, "Understand"),
            ("AU", "short", "Start with 4321. Reverse it and subtract the smaller from the larger. Write the answer.", [], "4321 − 1234 = 3087.", "1 mark for setting up; 1 mark for 3087.", 2, "Apply"),
            ("CT", "short", "Is the claim 'every 3-digit palindrome is divisible by 11' true? Test 121 and 131 and conclude.", [], "121 = 11 × 11 is divisible, but 131 is not, so the claim is false.", "1 mark for testing; 1 mark for the correct conclusion with counter-example.", 2, "Evaluate"),
        ]},
        {"title": "Data Handling and Presentation", "taught_by": 8, "questions": [
            ("LU", "mcq", "In a pictograph, one symbol stands for 5 students. Three and a half symbols stand for", ["17 or 18 students (17.5)", "35 students", "8 students", "15 students"], "17 or 18 students (17.5)", "1 mark for the correct option.", 1, "Understand"),
            ("CU", "short", "Why should the bars in a bar graph have equal width?", [], "Only the height should show the value; unequal widths would make some bars look bigger than their value.", "2 marks for the fairness/comparison reason.", 2, "Understand"),
            ("AU", "short", "Marks of 8 students: 7, 9, 6, 9, 10, 8, 9, 6. Make a tally table and name the mark scored most often.", [], "6: 2, 7: 1, 8: 1, 9: 3, 10: 1. The most frequent mark is 9.", "2 marks for the tally table; 1 mark for 9.", 3, "Apply"),
            ("CT", "short", "A bar graph of rainfall starts its scale at 50 mm instead of 0. Why can this be misleading?", [], "Small differences look large because the bottom of every bar is cut off; readers may think one month had several times more rain.", "2 marks for explaining the distortion.", 2, "Analyze"),
        ]},
        {"title": "Prime Time", "taught_by": 9, "questions": [
            ("LU", "mcq", "Which of these is a prime number?", ["29", "21", "27", "33"], "29", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why is 1 neither prime nor composite?", [], "A prime has exactly two factors and a composite has more than two; 1 has only one factor.", "2 marks for the factor-count reason.", 2, "Understand"),
            ("AU", "short", "Find the prime factorisation of 84.", [], r"\( 84 = 2 \times 2 \times 3 \times 7 \)", "1 mark for method; 2 marks for the correct factorisation.", 3, "Apply"),
            ("CT", "short", "Two buses leave a stop every 6 and 8 minutes. Rahul says they will next leave together after 48 minutes. Is he right?", [], "No. They meet after the LCM of 6 and 8, which is 24 minutes; 48 is a later common time, not the next one.", "1 mark for LCM 24; 1 mark for the judgement.", 2, "Evaluate"),
        ]},
        {"title": "Perimeter and Area", "taught_by": 11, "questions": [
            ("LU", "mcq", "The distance around a closed shape is its", ["perimeter", "area", "volume", "diagonal"], "perimeter", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Can two rectangles have the same perimeter but different areas? Give an example.", [], "Yes: 6 × 2 and 4 × 4 both have perimeter 16 cm, but areas 12 cm² and 16 cm².", "1 mark for yes; 1 mark for a correct example.", 2, "Understand"),
            ("AU", "short", r"A rectangular garden is \( 15\,\text{m} \) by \( 8\,\text{m} \). Fencing costs ₹40 per metre. Find the cost of fencing.", [], r"Perimeter \( = 2(15+8) = 46\,\text{m} \); cost \( = 46 \times 40 = ₹1840 \).", "1 mark perimeter formula; 1 mark 46 m; 1 mark ₹1840.", 3, "Apply"),
            ("CT", "short", "Sana doubles each side of a square. She says the area also doubles. Check with a 3 cm square and correct her.", [], "3 cm square: 9 cm²; 6 cm square: 36 cm², which is 4 times. Doubling sides makes the area four times.", "1 mark for the calculation; 1 mark for the correction.", 2, "Evaluate"),
        ]},
    ],
    (7, "sub-math"): [
        {"title": "Large Numbers Around Us", "taught_by": 4, "questions": [
            ("LU", "mcq", "In the Indian system, 10,00,000 is read as", ["ten lakh", "one crore", "one million thousand", "hundred thousand"], "ten lakh", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "How many lakhs make one crore? Explain using place value.", [], "100 lakhs; 1 crore = 1,00,00,000 = 100 × 1,00,000.", "2 marks for the place-value explanation.", 2, "Understand"),
            ("AU", "short", "A city's population is 23,45,678. Round it to the nearest lakh and write it in words.", [], "23,00,000 — twenty-three lakh.", "1 mark for rounding; 1 mark for words.", 2, "Apply"),
            ("CT", "short", "A news report says 'about 1 crore people' watched a match when the exact figure was 96,40,000. Is the rounding reasonable? Why?", [], "Yes: 96.4 lakh is close to 100 lakh (1 crore); the error is under 4%, fine for a headline.", "1 mark for judgement; 1 mark for the reason.", 2, "Evaluate"),
        ]},
        {"title": "Arithmetic Expressions", "taught_by": 5, "questions": [
            ("LU", "mcq", r"Which expression means 'subtract 5 from the product of 4 and 7'?", [r"\( 4 \times 7 - 5 \)", r"\( 5 - 4 \times 7 \)", r"\( 4 \times (7 - 5) \)", r"\( 4 + 7 - 5 \)"], r"\( 4 \times 7 - 5 \)", "1 mark for the correct option.", 1, "Understand"),
            ("CU", "short", r"Why do \( 30 - (10 - 4) \) and \( 30 - 10 - 4 \) give different answers?", [], "Brackets are evaluated first: 30 − 6 = 24, while 30 − 10 − 4 = 16. Subtraction is not associative.", "1 mark each value; 1 mark reason.", 3, "Understand"),
            ("AU", "short", "Sohan buys 3 notebooks at ₹45 each and pays with ₹200. Write an expression for the change and evaluate it.", [], r"\( 200 - 3 \times 45 = 65 \); change is ₹65.", "1 mark expression; 1 mark ₹65.", 2, "Apply"),
            ("CT", "short", r"Is \( 12 \div 3 \times 2 \) equal to 8 or 2? Explain which is correct.", [], "8: division and multiplication are done left to right, so (12 ÷ 3) × 2 = 8.", "1 mark answer; 1 mark reason.", 2, "Analyze"),
        ]},
        {"title": "A Peek Beyond the Point", "taught_by": 7, "questions": [
            ("LU", "mcq", "In 4.075, the digit 7 is in the", ["hundredths place", "tenths place", "thousandths place", "ones place"], "hundredths place", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Which is greater, 0.5 or 0.45? Explain using place value.", [], "0.5 = 0.50; 50 hundredths is more than 45 hundredths, so 0.5 is greater.", "2 marks for the place-value comparison.", 2, "Understand"),
            ("AU", "short", "A ribbon is 2.35 m long. Priya cuts 0.8 m from it. How much is left?", [], "2.35 − 0.80 = 1.55 m.", "1 mark aligning decimals; 1 mark 1.55 m.", 2, "Apply"),
            ("CT", "short", "Karan says 0.10 is greater than 0.9 because 10 is greater than 9. Find his mistake.", [], "He compared digits as whole numbers; 0.9 = 0.90, which is 90 hundredths, more than 10 hundredths.", "2 marks for identifying the place-value error.", 2, "Evaluate"),
        ]},
        {"title": "Expressions using Letter-Numbers", "taught_by": 8, "questions": [
            ("LU", "mcq", "If a pen costs ₹p, the cost of 5 pens is", ["5p", "p + 5", "p − 5", "p/5"], "5p", "1 mark for the correct option.", 1, "Understand"),
            ("CU", "short", r"Why are \( 3x + 2x \) and \( 5x \) the same for every value of x?", [], "Both mean 5 groups of x: 3 groups plus 2 groups. They are like terms.", "2 marks for the like-terms explanation.", 2, "Understand"),
            ("AU", "short", r"Find the value of \( 4a - 3b \) when \( a = 5 \) and \( b = 2 \).", [], r"\( 4 \times 5 - 3 \times 2 = 20 - 6 = 14 \)", "1 mark substitution; 1 mark 14.", 2, "Apply"),
            ("CT", "short", "Matchstick squares in a row need 4, 7, 10, … sticks. Ravi writes 4n. Check his formula for 2 squares and correct it.", [], "4n gives 8 for n = 2, but 7 sticks are needed. The correct rule is 3n + 1.", "1 mark testing; 1 mark correct rule.", 2, "Evaluate"),
        ]},
        {"title": "Parallel and Intersecting Lines", "taught_by": 9, "questions": [
            ("LU", "mcq", "Two lines in a plane that never meet are called", ["parallel lines", "intersecting lines", "perpendicular lines", "transversals"], "parallel lines", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "When a transversal cuts two parallel lines, why are corresponding angles equal?", [], "The transversal crosses both lines in the same direction, so the angle it makes with each parallel line is the same.", "2 marks for a sound reason.", 2, "Understand"),
            ("AU", "short", "Two parallel lines are cut by a transversal. One interior angle is 65°. Find the co-interior angle on the same side.", [], "180° − 65° = 115°.", "1 mark rule; 1 mark 115°.", 2, "Apply"),
            ("CT", "short", "Alternate angles formed by two lines and a transversal are 70° and 75°. Are the lines parallel? Justify.", [], "No; for parallel lines alternate angles must be equal.", "2 marks for the justified conclusion.", 2, "Evaluate"),
        ]},
    ],
    (8, "sub-math"): [
        {"title": "A Square and A Cube", "taught_by": 4, "questions": [
            ("LU", "mcq", "Which of these is a perfect cube?", ["125", "100", "150", "81"], "125", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why can a perfect square never end in the digit 7?", [], "Squares of the units digits 0–9 end only in 0, 1, 4, 5, 6 or 9, never 7.", "2 marks for the units-digit argument.", 2, "Understand"),
            ("AU", "short", r"Find \( \sqrt{1764} \) by prime factorisation.", [], r"\( 1764 = 2^2 \times 3^2 \times 7^2 \), so \( \sqrt{1764} = 2 \times 3 \times 7 = 42 \).", "2 marks factorisation; 1 mark 42.", 3, "Apply"),
            ("CT", "short", "Anu says the square of an even number is always even and the square of an odd number is always odd. Justify or disprove.", [], "True: even × even is even; odd × odd is odd because (2k+1)² = 4k² + 4k + 1.", "1 mark each case.", 2, "Evaluate"),
        ]},
        {"title": "Power Play", "taught_by": 5, "questions": [
            ("LU", "mcq", r"\( 2^5 \) means", ["2 multiplied by itself 5 times", "2 × 5", "5 multiplied by itself 2 times", "2 + 5"], "2 multiplied by itself 5 times", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", r"Explain why \( a^0 = 1 \) using \( a^3 \div a^3 \).", [], r"\( a^3 \div a^3 = a^{3-3} = a^0 \), and any non-zero number divided by itself is 1.", "2 marks for the law-of-exponents explanation.", 2, "Understand"),
            ("AU", "short", r"Simplify \( \dfrac{3^7 \times 3^2}{3^5} \).", [], r"\( 3^{7+2-5} = 3^4 = 81 \)", "1 mark exponent rule; 1 mark 81.", 2, "Apply"),
            ("CT", "short", "A sheet of paper 0.1 mm thick is folded in half 10 times. Is the stack thicker than 10 cm? Show your reasoning.", [], r"Thickness \( = 0.1 \times 2^{10} = 102.4\,\text{mm} \approx 10.2\,\text{cm} \), just over 10 cm.", "1 mark doubling idea; 1 mark conclusion.", 2, "Analyze"),
        ]},
        {"title": "A Story of Numbers", "taught_by": 7, "questions": [
            ("LU", "mcq", "The Hindu-Arabic numeral system is a", ["place-value system with a symbol for zero", "system without zero", "tally system", "Roman numeral system"], "place-value system with a symbol for zero", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why was the invention of zero important for writing large numbers?", [], "Zero holds an empty place, so 205 and 25 can be told apart; this makes place-value notation work for any size of number.", "2 marks for the placeholder idea.", 2, "Understand"),
            ("AU", "short", "Write 47 in base 2 (binary).", [], "101111", "1 mark method; 1 mark answer.", 2, "Apply"),
            ("CT", "short", "Compare Roman numerals and our place-value system for adding 1999 + 2026. Which is easier and why?", [], "Place value: digits line up by place and carry. Roman numerals (MCMXCIX) have no place value, so column addition is not possible.", "2 marks for a reasoned comparison.", 2, "Evaluate"),
        ]},
        {"title": "Quadrilaterals", "taught_by": 8, "questions": [
            ("LU", "mcq", "A quadrilateral with exactly one pair of parallel sides is a", ["trapezium", "parallelogram", "rhombus", "kite"], "trapezium", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why is every square a rectangle, but not every rectangle a square?", [], "A square has four right angles like a rectangle, and also four equal sides; a rectangle need not have equal sides.", "2 marks for the property comparison.", 2, "Understand"),
            ("AU", "short", "Three angles of a quadrilateral are 75°, 90° and 105°. Find the fourth angle.", [], "360° − (75 + 90 + 105)° = 90°.", "1 mark angle-sum 360°; 1 mark 90°.", 2, "Apply"),
            ("CT", "short", "A shape has diagonals that bisect each other at right angles. Must it be a square? Explain.", [], "Not necessarily: it is a rhombus. It is a square only if the diagonals are also equal.", "2 marks for the rhombus/square distinction.", 2, "Analyze"),
        ]},
        {"title": "Proportional Reasoning-1", "taught_by": 10, "questions": [
            ("LU", "mcq", "If 3 pens cost ₹45, the cost of 1 pen is found by", ["dividing 45 by 3", "multiplying 45 by 3", "adding 45 and 3", "subtracting 3 from 45"], "dividing 45 by 3", "1 mark for the correct option.", 1, "Understand"),
            ("CU", "short", "What does it mean for two quantities to be in direct proportion?", [], "When one increases or decreases, the other changes by the same factor, so their ratio stays constant.", "2 marks for the constant-ratio idea.", 2, "Understand"),
            ("AU", "short", "A car uses 6 litres of petrol for 90 km. How much petrol is needed for 240 km?", [], r"\( 6 \times 240 / 90 = 16 \) litres.", "1 mark setup; 1 mark 16 litres.", 2, "Apply"),
            ("CT", "short", "8 workers build a wall in 6 days. Neha says 16 workers need 12 days. Find her error.", [], "Workers and days are in inverse proportion; 16 workers need 3 days, not 12.", "2 marks for identifying inverse proportion and the right answer.", 2, "Evaluate"),
        ]},
    ],
    # ------------------------------------------------------------------ Science
    (6, "sub-sci"): [
        {"title": "The Wonderful World of Science", "taught_by": 4, "questions": [
            ("LU", "mcq", "The first step of finding things out in science is usually to", ["ask a question", "write the answer", "skip observation", "guess and stop"], "ask a question", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why should an experiment be repeated more than once?", [], "To check that the result was not a chance or measurement error; repeated results are more reliable.", "2 marks for the reliability idea.", 2, "Understand"),
            ("AU", "short", "Plan a simple test to find out whether seeds need water to sprout.", [], "Keep two sets of the same seeds on cotton, water one set and keep the other dry, with everything else the same; observe for 4–5 days.", "1 mark two groups; 1 mark only water changed.", 2, "Apply"),
            ("CT", "short", "Rohan's plant grew taller after he played music to it once. Can he conclude music makes plants grow? Explain.", [], "No: one plant and one trial without a comparison plant cannot show cause; sunlight or water may have caused the growth.", "2 marks for the fair-test reasoning.", 2, "Evaluate"),
        ]},
        {"title": "Diversity in the Living World", "taught_by": 5, "questions": [
            ("LU", "mcq", "Plants that have weak stems and need support to climb are called", ["climbers", "shrubs", "trees", "herbs"], "climbers", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why do desert plants like cactus have spines instead of broad leaves?", [], "Spines reduce the surface from which water evaporates, helping the plant save water.", "2 marks for the water-loss reason.", 2, "Understand"),
            ("AU", "short", "Classify: mango, tulsi, money plant, rose — into tree, shrub, herb, climber.", [], "Mango: tree; rose: shrub; tulsi: herb (shrubby herb); money plant: climber.", "1/2 mark each.", 2, "Apply"),
            ("CT", "short", "A student groups animals as 'useful' and 'harmful'. Why is this not a scientific way of grouping?", [], "It depends on human opinion, not on observable features like body structure or habitat; the same animal may be both.", "2 marks for the feature-based grouping argument.", 2, "Evaluate"),
        ]},
        {"title": "Mindful Eating: A Path to a Healthy Body", "taught_by": 7, "questions": [
            ("LU", "mcq", "Iodine solution turns blue-black when it is added to food containing", ["starch", "protein", "fat", "vitamin C"], "starch", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why is a balanced diet important for a growing child?", [], "It provides all nutrients — carbohydrates, proteins, fats, vitamins, minerals, water and roughage — in the right amounts for growth and health.", "2 marks naming nutrients and purpose.", 2, "Understand"),
            ("AU", "short", "Suggest one change to a lunch of only rice and pickle to make it balanced.", [], "Add dal (protein), a vegetable sabzi or salad (vitamins, minerals, roughage) and curd.", "2 marks for adding missing nutrient groups.", 2, "Apply"),
            ("CT", "short", "An advertisement says a packaged juice is 'healthier than fruit'. How would you check this claim?", [], "Compare the label (sugar, fibre, preservatives) with fresh fruit; fresh fruit has fibre and no added sugar, so the claim is doubtful.", "2 marks for evidence-based checking.", 2, "Evaluate"),
        ]},
        {"title": "Exploring Magnets", "taught_by": 8, "questions": [
            ("LU", "mcq", "The ends of a bar magnet are called its", ["poles", "edges", "tips", "corners"], "poles", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why does a freely suspended bar magnet always point north–south?", [], "The Earth behaves like a huge magnet; the magnet's poles are attracted towards the Earth's opposite magnetic poles.", "2 marks for the Earth-magnet explanation.", 2, "Understand"),
            ("AU", "short", "How can you find which end of an unmarked magnet is its north pole using a compass?", [], "Bring the magnet's end near the compass; the end that attracts the compass's south (non-pointer) end, i.e. repels the north-pointing needle, is the north pole.", "2 marks for a correct method.", 2, "Apply"),
            ("CT", "short", "Attraction alone is not a sure test of a magnet, but repulsion is. Why?", [], "A magnet attracts unmagnetised iron too, but only two magnets can repel each other.", "2 marks for the reasoning.", 2, "Analyze"),
        ]},
        {"title": "Measurement of Length and Motion", "taught_by": 9, "questions": [
            ("LU", "mcq", "The SI unit of length is the", ["metre", "kilogram", "second", "litre"], "metre", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why are hand spans not a good unit for measuring length?", [], "Hand spans differ from person to person, so the same length gives different measurements.", "2 marks for the standard-unit idea.", 2, "Understand"),
            ("AU", "short", "A pencil starts at 1.0 cm on a scale and ends at 13.5 cm. What is its length?", [], "13.5 − 1.0 = 12.5 cm.", "1 mark subtraction; 1 mark 12.5 cm.", 2, "Apply"),
            ("CT", "short", "Classify the motion of a ceiling fan blade, a swing and a train on a straight track. Can one object show two types of motion?", [], "Circular, periodic (oscillatory), straight-line (linear). Yes — a bicycle wheel rotates while the bicycle moves in a straight line.", "1 mark classification; 1 mark example.", 2, "Analyze"),
        ]},
        {"title": "Materials Around Us", "taught_by": 11, "questions": [
            ("LU", "mcq", "A material through which we can see clearly is", ["transparent", "opaque", "translucent", "lustrous"], "transparent", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why are cooking pans made of metal but their handles of plastic or wood?", [], "Metals conduct heat to cook food; plastic and wood are poor conductors, so the handle stays cool.", "2 marks for the conduction reason.", 2, "Understand"),
            ("AU", "short", "Group: glass, wood, steel spoon, oil, sugar into 'sinks/floats in water' with a reason.", [], "Glass and steel sink (denser); wood and oil float (less dense); sugar dissolves.", "2 marks for correct grouping.", 2, "Apply"),
            ("CT", "short", "Should schools replace plastic water bottles with steel ones? Give one argument for and one against.", [], "For: steel is durable, reusable and reduces plastic waste. Against: it is heavier and costs more.", "1 mark each argument.", 2, "Evaluate"),
        ]},
    ],
    (7, "sub-sci"): [
        {"title": "The Ever-Evolving World of Science", "taught_by": 4, "questions": [
            ("LU", "mcq", "A possible explanation that can be tested by an experiment is called a", ["hypothesis", "conclusion", "law", "fact"], "hypothesis", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why do scientific ideas sometimes change over time?", [], "New observations and better instruments give new evidence; ideas are updated to fit the evidence.", "2 marks for the evidence idea.", 2, "Understand"),
            ("AU", "short", "Write a hypothesis and a test for: 'Does salt make ice melt faster?'", [], "Hypothesis: salt makes ice melt faster. Test: two equal ice cubes, sprinkle salt on one, time how long each takes to melt.", "1 mark hypothesis; 1 mark fair test.", 2, "Apply"),
            ("CT", "short", "Why is it important for scientists to share their methods, not only their results?", [], "Others can repeat the experiment and check the result, which catches errors and builds trust.", "2 marks for reproducibility.", 2, "Evaluate"),
        ]},
        {"title": "Exploring Substances: Acidic, Basic, and Neutral", "taught_by": 5, "questions": [
            ("LU", "mcq", "Blue litmus paper turns red in", ["an acid", "a base", "pure water", "salt solution"], "an acid", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What happens in neutralisation? Give one everyday example.", [], "An acid reacts with a base to form salt and water; e.g. an antacid relieves acidity in the stomach.", "1 mark definition; 1 mark example.", 2, "Understand"),
            ("AU", "short", "Turmeric paper turns red when dipped in soap solution. What does this tell you about soap?", [], "Soap solution is basic.", "2 marks for 'basic' with indicator reasoning.", 2, "Apply"),
            ("CT", "short", "A farmer's soil is too acidic. Suggest a treatment and explain why it works.", [], "Add quicklime or slaked lime (a base); it neutralises the excess acid in the soil.", "1 mark treatment; 1 mark neutralisation reason.", 2, "Evaluate"),
        ]},
        {"title": "Electricity: Circuits and their Components", "taught_by": 7, "questions": [
            ("LU", "mcq", "A device that opens or closes an electric circuit is a", ["switch", "bulb", "cell", "wire"], "switch", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why does a bulb not glow when the switch is open?", [], "An open switch breaks the circuit, so current cannot flow through the bulb.", "2 marks for the closed-circuit idea.", 2, "Understand"),
            ("AU", "short", "Draw (describe) a circuit diagram with one cell, one switch and two bulbs in series.", [], "Cell → switch → bulb 1 → bulb 2 → back to cell, in one loop, using standard symbols.", "2 marks for a correct series loop.", 2, "Apply"),
            ("CT", "short", "In a series string of decorative lights, one bulb fuses and all go off. Explain and suggest a better arrangement.", [], "In series there is only one path, so a break stops all current. Connecting bulbs in parallel keeps others glowing.", "1 mark explanation; 1 mark parallel suggestion.", 2, "Evaluate"),
        ]},
        {"title": "The World of Metals and Non-metals", "taught_by": 8, "questions": [
            ("LU", "mcq", "The property of metals by which they can be drawn into wires is", ["ductility", "malleability", "sonority", "lustre"], "ductility", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why does iron rust but gold does not?", [], "Iron reacts with oxygen and moisture to form rust; gold is very unreactive.", "2 marks for the reactivity idea.", 2, "Understand"),
            ("AU", "short", "Suggest two ways to protect an iron gate from rusting.", [], "Paint it, or galvanise it with zinc (or apply grease/oil).", "1 mark per method.", 2, "Apply"),
            ("CT", "short", "Electric wires are made of copper, not iron, although iron is cheaper. Why?", [], "Copper conducts electricity much better and does not rust, so less energy is wasted and the wire lasts longer.", "2 marks for conductivity + durability.", 2, "Evaluate"),
        ]},
        {"title": "Changes Around Us: Physical and Chemical", "taught_by": 9, "questions": [
            ("LU", "mcq", "Which of these is a chemical change?", ["burning of paper", "melting of ice", "tearing of paper", "dissolving sugar"], "burning of paper", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "How is a physical change different from a chemical change?", [], "In a physical change no new substance forms and it is often reversible; a chemical change forms new substances.", "2 marks for the new-substance distinction.", 2, "Understand"),
            ("AU", "short", "Is cooking an egg a physical or chemical change? Give one sign.", [], "Chemical: the egg white changes permanently from clear liquid to white solid; it cannot be reversed.", "2 marks with evidence.", 2, "Apply"),
            ("CT", "short", "Crystallisation gives pure copper sulphate from an impure sample. Is this a physical or chemical change? Justify.", [], "Physical: the same substance separates as crystals; no new substance forms.", "2 marks for justified classification.", 2, "Analyze"),
        ]},
    ],
    (8, "sub-sci"): [
        {"title": "Exploring the Investigative World of Science", "taught_by": 4, "questions": [
            ("LU", "mcq", "In a fair test, the factor that is deliberately changed is the", ["independent variable", "dependent variable", "controlled variable", "result"], "independent variable", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why must other variables be kept the same in a fair test?", [], "So that any change in the result can be linked only to the variable that was changed.", "2 marks for the cause-isolation idea.", 2, "Understand"),
            ("AU", "short", "Design a fair test to check whether the colour of a cloth affects how quickly it dries.", [], "Same size and fabric, different colours only, equal water, same place and time; measure drying time.", "2 marks for variables controlled.", 2, "Apply"),
            ("CT", "short", "A study of 5 students claims a new pen improves handwriting. Give two weaknesses of the study.", [], "Sample too small; no comparison group / handwriting judged by opinion; other factors not controlled.", "1 mark per weakness.", 2, "Evaluate"),
        ]},
        {"title": "The Invisible Living World: Beyond Our Naked Eye", "taught_by": 5, "questions": [
            ("LU", "mcq", "Curd is formed from milk by the action of", ["Lactobacillus bacteria", "yeast", "virus", "algae"], "Lactobacillus bacteria", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why do bread doughs with yeast rise?", [], "Yeast respires and produces carbon dioxide gas, which forms bubbles that make the dough rise.", "2 marks for CO₂ by respiration.", 2, "Understand"),
            ("AU", "short", "Give two ways to prevent food from spoiling due to microorganisms at home.", [], "Refrigeration; boiling/pasteurisation; adding salt, sugar or oil (pickles); keeping food covered.", "1 mark per method.", 2, "Apply"),
            ("CT", "short", "Should antibiotics be taken for a common cold? Explain.", [], "No: colds are caused by viruses, and antibiotics act on bacteria; misuse also builds antibiotic resistance.", "2 marks for virus/bacteria and resistance.", 2, "Evaluate"),
        ]},
        {"title": "Health: The Ultimate Treasure", "taught_by": 7, "questions": [
            ("LU", "mcq", "Diseases that spread from one person to another are called", ["communicable diseases", "deficiency diseases", "genetic disorders", "lifestyle diseases"], "communicable diseases", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "How does vaccination protect us from a disease?", [], "A vaccine trains the body's immune system to recognise the germ, so it can fight a later infection quickly.", "2 marks for the immune-memory idea.", 2, "Understand"),
            ("AU", "short", "List three steps a school can take to prevent the spread of dengue.", [], "Remove stagnant water, use mosquito nets/repellents, wear full sleeves, spray larvicide in drains.", "1 mark per step (max 3).", 3, "Apply"),
            ("CT", "short", "Is 'feeling fine' enough evidence of being healthy? Discuss using the idea of mental and social well-being.", [], "No: health includes physical, mental and social well-being; a person may feel fine physically but face stress or isolation.", "2 marks for the multi-dimensional view.", 2, "Evaluate"),
        ]},
        {"title": "Electricity: Magnetic and Heating Effects", "taught_by": 8, "questions": [
            ("LU", "mcq", "An electric heater works on the", ["heating effect of current", "magnetic effect of current", "chemical effect of current", "lighting effect"], "heating effect of current", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why does a fuse wire melt when too much current flows?", [], "Large current produces a lot of heat; the fuse wire has a low melting point, so it melts and breaks the circuit.", "2 marks for heat + low melting point.", 2, "Understand"),
            ("AU", "short", "How can you make an electromagnet stronger? Give two ways.", [], "Increase the number of turns of wire, use a soft-iron core, or increase the current.", "1 mark per way.", 2, "Apply"),
            ("CT", "short", "Why are electromagnets, not permanent magnets, used in scrap-yard cranes?", [], "An electromagnet can be switched off to drop the load and its strength can be controlled.", "2 marks for switching/control.", 2, "Evaluate"),
        ]},
        {"title": "Exploring Forces", "taught_by": 9, "questions": [
            ("LU", "mcq", "The SI unit of force is the", ["newton", "pascal", "joule", "watt"], "newton", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why do tyres of vehicles have treads?", [], "Treads increase friction with the road, giving better grip and preventing skidding.", "2 marks for friction/grip.", 2, "Understand"),
            ("AU", "short", "Two children push a box with 30 N and 20 N in opposite directions. Find the net force and its direction.", [], "10 N in the direction of the 30 N push.", "1 mark magnitude; 1 mark direction.", 2, "Apply"),
            ("CT", "short", "A ball rolling on the ground slows down and stops. Ayaan says no force acted on it. Is he right?", [], "No: friction acted opposite to the motion and slowed the ball.", "2 marks for identifying friction.", 2, "Evaluate"),
        ]},
    ],
    # ------------------------------------------------------------------ English (Poorvi)
    **{(g, "sub-eng"): [
        {"title": "Unit 1: Fables and Folk Tales" if g == 6 else ("Unit 1: Learning Together" if g == 7 else "Unit 1: Wit and Humour"), "taught_by": 5, "questions": [
            ("LU", "short", "Read: 'The crow was clever; it dropped pebbles into the pitcher until the water rose.' What does 'clever' tell us about the crow?", [], "The crow was intelligent and found a smart way to solve its problem.", "2 marks for inference from the word.", 2, "Understand"),
            ("CU", "short", "What is the moral of a fable? Give an example from any fable you have read.", [], "A fable teaches a lesson, e.g. 'slow and steady wins the race' from The Hare and the Tortoise.", "1 mark meaning; 1 mark example.", 2, "Understand"),
            ("AU", "short", "Rewrite in passive voice: 'The teacher praised the students.'", [], "The students were praised by the teacher.", "2 marks for correct passive form.", 2, "Apply"),
            ("CT", "short", "The hare lost because he was overconfident. Do you think overconfidence is always harmful? Give your opinion with one reason.", [], "Any reasoned opinion, e.g. confidence helps but overconfidence makes us careless and stop preparing.", "1 mark opinion; 1 mark reason.", 2, "Evaluate"),
        ]},
        {"title": "Unit 2: Friendship" if g == 6 else ("Unit 2: Wit and Wisdom" if g == 7 else "Unit 2: Values and Dispositions"), "taught_by": 8, "questions": [
            ("LU", "mcq", "Choose the synonym of 'loyal':", ["faithful", "careless", "angry", "selfish"], "faithful", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What qualities make someone a good friend? Name two and explain one.", [], "Honesty and kindness; e.g. an honest friend tells you the truth even when it is hard.", "1 mark qualities; 1 mark explanation.", 2, "Understand"),
            ("AU", "short", "Write a short message (40 words) inviting your friend to your school's science exhibition.", [], "A message with date, time, place, purpose and a friendly closing.", "1 mark content; 1 mark format.", 2, "Apply"),
            ("CT", "short", "Is it right to keep a friend's secret if it may harm them? Give your view.", [], "Reasoned view, e.g. safety comes first, so tell a trusted adult while being kind to the friend.", "1 mark view; 1 mark reason.", 2, "Evaluate"),
        ]},
    ] for g in (6, 7, 8)},
    # ------------------------------------------------------------------ Social Science
    (6, "sub-sst"): [
        {"title": "Locating Places on the Earth", "taught_by": 5, "questions": [
            ("LU", "mcq", "Imaginary lines running east–west around the globe are called", ["latitudes", "longitudes", "meridians", "axes"], "latitudes", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "Why do we need both latitude and longitude to locate a place?", [], "Latitude gives the north–south position and longitude the east–west position; together they fix one exact point.", "2 marks for the grid idea.", 2, "Understand"),
            ("AU", "short", "India's Standard Meridian is 82°30′E. Why was one meridian chosen for the whole country?", [], "To have one standard time for the whole country, avoiding confusion between regions.", "2 marks for standard time.", 2, "Apply"),
            ("CT", "short", "Some people suggest India should have two time zones. Give one advantage and one disadvantage.", [], "Advantage: better use of daylight in the north-east. Disadvantage: confusion in railways, offices and communication.", "1 mark each.", 2, "Evaluate"),
        ]},
        {"title": "Timeline and Sources of History", "taught_by": 8, "questions": [
            ("LU", "mcq", "Coins, inscriptions and monuments are examples of", ["archaeological sources", "literary sources", "oral sources", "maps"], "archaeological sources", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What does BCE mean, and how do we count years in BCE?", [], "Before Common Era; years are counted backwards, so 500 BCE is earlier than 200 BCE.", "2 marks for meaning + direction.", 2, "Understand"),
            ("AU", "short", "How many years passed between 300 BCE and 200 CE?", [], "500 years (300 + 200, there is no year zero in common counting; accept 499/500 with reasoning).", "2 marks for correct calculation.", 2, "Apply"),
            ("CT", "short", "Why should historians use more than one source to study an event?", [], "Each source may be incomplete or biased; comparing sources gives a more reliable picture.", "2 marks for corroboration.", 2, "Evaluate"),
        ]},
    ],
    (7, "sub-sst"): [
        {"title": "Geographical Diversity of India", "taught_by": 5, "questions": [
            ("LU", "mcq", "The Thar Desert lies mainly in the state of", ["Rajasthan", "Kerala", "Assam", "Odisha"], "Rajasthan", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "How do the Himalayas affect India's climate?", [], "They block cold winds from Central Asia and make monsoon winds shed rain over the plains.", "2 marks for both effects.", 2, "Understand"),
            ("AU", "short", "Name the physical region where you would expect stepped (terrace) farming and explain why.", [], "Himalayan region (e.g. Himachal Pradesh); slopes are cut into steps to hold soil and water.", "1 mark region; 1 mark reason.", 2, "Apply"),
            ("CT", "short", "Should more hydro-power dams be built in the Himalayas? Give one point for and one against.", [], "For: clean electricity. Against: landslides, displacement, damage to fragile ecosystems.", "1 mark each.", 2, "Evaluate"),
        ]},
        {"title": "Understanding the Weather", "taught_by": 8, "questions": [
            ("LU", "mcq", "The instrument used to measure rainfall is a", ["rain gauge", "barometer", "thermometer", "wind vane"], "rain gauge", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What is the difference between weather and climate?", [], "Weather is the day-to-day condition of the atmosphere; climate is the average weather over many years.", "2 marks for the time-scale difference.", 2, "Understand"),
            ("AU", "short", "The temperatures for a week were 30, 32, 31, 29, 33, 34, 32 °C. Find the average.", [], "221 ÷ 7 ≈ 31.6 °C.", "1 mark sum; 1 mark average.", 2, "Apply"),
            ("CT", "short", "Why are weather forecasts sometimes wrong even with satellites?", [], "The atmosphere changes rapidly and small changes can grow; forecasts are probabilities, not certainties.", "2 marks for uncertainty reasoning.", 2, "Evaluate"),
        ]},
    ],
    (8, "sub-sst"): [
        {"title": "Natural Resources and Their Use", "taught_by": 5, "questions": [
            ("LU", "mcq", "Coal and petroleum are examples of", ["non-renewable resources", "renewable resources", "human-made resources", "biotic resources"], "non-renewable resources", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What is sustainable use of resources?", [], "Using resources to meet present needs while leaving enough for future generations.", "2 marks for the future-generations idea.", 2, "Understand"),
            ("AU", "short", "Suggest three ways your school can save water.", [], "Fix leaking taps, rainwater harvesting, reuse RO waste water for gardening, awareness posters.", "1 mark each (max 3).", 3, "Apply"),
            ("CT", "short", "Is solar energy a complete solution to India's energy needs? Discuss.", [], "Helpful and renewable, but depends on sunlight, needs storage and land; a mix of sources is needed.", "2 marks for a balanced argument.", 2, "Evaluate"),
        ]},
        {"title": "Universal Franchise and India's Electoral System", "taught_by": 8, "questions": [
            ("LU", "mcq", "In India, the minimum age to vote is", ["18 years", "21 years", "16 years", "25 years"], "18 years", "1 mark for the correct option.", 1, "Remember"),
            ("CU", "short", "What does 'universal adult franchise' mean?", [], "Every adult citizen has the right to vote, regardless of religion, caste, gender, wealth or education.", "2 marks for the equality idea.", 2, "Understand"),
            ("AU", "short", "List the steps a voter follows on polling day.", [], "Show ID, name checked in the voter list, ink on finger, vote on the EVM, check the VVPAT slip.", "2 marks for a correct sequence.", 2, "Apply"),
            ("CT", "short", "Why is a secret ballot important in a democracy?", [], "Voters can choose freely without fear or pressure; it prevents bribery and intimidation.", "2 marks for free choice reasoning.", 2, "Evaluate"),
        ]},
    ],
    # ------------------------------------------------------------------ Hindi (मल्हार)
    **{(g, "sub-hin"): [
        {"title": "पाठ 1: " + ("मातृभूमि" if g == 6 else ("माँ, कह एक कहानी" if g == 7 else "स्वदेश")), "taught_by": 5, "questions": [
            ("LU", "mcq", "'मातृभूमि' शब्द का अर्थ है —", ["जन्मभूमि / अपना देश", "माँ का घर", "विदेश", "खेत"], "जन्मभूमि / अपना देश", "सही विकल्प के लिए 1 अंक।", 1, "Remember"),
            ("CU", "short", "कविता में देश की प्रशंसा किन-किन बातों से की गई है? दो बातें लिखिए।", [], "प्राकृतिक सुंदरता (नदियाँ, पर्वत, खेत) और लोगों की वीरता / संस्कृति।", "प्रत्येक बात के लिए 1 अंक।", 2, "Understand"),
            ("AU", "short", "'देश' शब्द से दो नए शब्द बनाइए और उनका वाक्य में प्रयोग कीजिए।", [], "देशभक्ति, देशवासी — उचित वाक्य प्रयोग।", "शब्द और वाक्य के लिए 2 अंक।", 2, "Apply"),
            ("CT", "short", "अपने देश से प्रेम दिखाने के लिए एक विद्यार्थी क्या-क्या कर सकता है? अपने विचार लिखिए।", [], "स्वच्छता, नियमों का पालन, पढ़ाई में मेहनत, दूसरों की मदद — तर्कसहित उत्तर।", "विचार और तर्क के लिए 2 अंक।", 2, "Evaluate"),
        ]},
        {"title": "पाठ 2: " + ("गोल" if g == 6 else ("तीन बुद्धिमान" if g == 7 else "दो गौरैया")), "taught_by": 8, "questions": [
            ("LU", "mcq", "'खिलाड़ी' शब्द में कौन-सा प्रत्यय है?", ["आड़ी", "खिल", "ई", "ड़ी"], "आड़ी", "सही विकल्प के लिए 1 अंक।", 1, "Remember"),
            ("CU", "short", "पाठ से हमें खेल-भावना के बारे में क्या सीख मिलती है?", [], "हार-जीत से ऊपर उठकर ईमानदारी और सम्मान से खेलना चाहिए।", "उचित सीख के लिए 2 अंक।", 2, "Understand"),
            ("AU", "short", "अपने विद्यालय के खेल-दिवस पर पाँच वाक्यों में एक अनुच्छेद लिखिए।", [], "खेल-दिवस का क्रमबद्ध वर्णन, उचित भाषा।", "विषय-वस्तु 1 अंक, भाषा 1 अंक।", 2, "Apply"),
            ("CT", "short", "क्या जीतना ही खेल का एकमात्र उद्देश्य है? अपने विचार दीजिए।", [], "नहीं — स्वास्थ्य, टीमवर्क, अनुशासन भी उद्देश्य हैं; तर्कसहित उत्तर।", "विचार और तर्क के लिए 2 अंक।", 2, "Evaluate"),
        ]},
    ] for g in (6, 7, 8)},
}


def chapters(grade: int, subject_id: str) -> List[dict]:
    return CONTENT.get((grade, subject_id), [])


def taught_chapters(grade: int, subject_id: str, by_month: int) -> List[dict]:
    """Chapters completed by `by_month` (April = 4 ... March = 3 is treated as 15)."""
    month = by_month if by_month >= 4 else by_month + 12
    return [c for c in chapters(grade, subject_id) if c["taught_by"] <= month]
