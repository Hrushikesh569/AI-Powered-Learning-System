import pandas as pd

# Load raw data
df = pd.read_csv("Raw_Responses/raw_google_form_export.csv")

# Remove incomplete rows
df = df.dropna()

# Ensure age range
df = df[(df["Age"] >= 19) & (df["Age"] <= 24)]

# Standardize categories
df["Tuition"] = df["Tuition"].str.strip().str.title()
df["University_Type"] = df["University_Type"].str.strip().str.title()

# Save cleaned file
df.to_csv("Cleaned_Data/university_student_stress_dataset.csv", index=False)
