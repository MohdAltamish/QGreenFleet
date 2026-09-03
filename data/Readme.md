# Data Setup
1. MRV: https://mrv.emsa.europa.eu/#public/emission-report
   Export 2022/2023/2024 -> save as data/raw/mrv_2022.xlsx etc.
2. Kaggle: "Ship Performance Clustering Dataset" -> data/raw/ship_performance.csv
3. Run: python -m src.data.prepare
4. Run: python -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42
raw/ and processed/ are gitignored; synthetic/ is committed.
