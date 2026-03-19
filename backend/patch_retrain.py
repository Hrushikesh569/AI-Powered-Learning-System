import os
import re

file_path = "backend/retrain_high_accuracy.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update _fe_progress to ensure 'difficulty' exists and include Riiid features
fe_prog_insertion = """    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes if "dataset" in df.columns else 0

    if "difficulty" not in df.columns:
        df["difficulty"] = 1.0 - df.groupby("question_id")["correct"].transform("mean")
    if "part" in df.columns:
        df["part"] = df["part"].fillna(0).astype(int)
    else:
        df["part"] = 0
    if "prior_question_elapsed_time" in df.columns:
        df["pq_time"] = df["prior_question_elapsed_time"].fillna(0)
    else:
        df["pq_time"] = 0
    if "prior_question_had_explanation" in df.columns:
        df["pq_exp"] = df["prior_question_had_explanation"].fillna(0).astype(int)
    else:
        df["pq_exp"] = 0

    FEAT_COLS = ["""

content = content.replace('    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes\n\n    FEAT_COLS = [', fe_prog_insertion)

# Update FEAT_COLS list for progress
feat_cols_original = '"user_cat", "question_cat", "dataset_cat",'
feat_cols_new = '"user_cat", "question_cat", "dataset_cat", "part", "pq_time", "pq_exp",'
content = content.replace(feat_cols_original, feat_cols_new)


# 2. Update _fe_reschedule to ensure 'difficulty' exists and include Riiid features
fe_resc_insertion = """    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes if "dataset" in df.columns else 0

    if "difficulty" not in df.columns:
        df["difficulty"] = 1.0 - df.groupby("question_id")["correct"].transform("mean")
    if "part" in df.columns:
        df["part"] = df["part"].fillna(0).astype(int)
    else:
        df["part"] = 0
    if "prior_question_elapsed_time" in df.columns:
        df["pq_time"] = df["prior_question_elapsed_time"].fillna(0)
    else:
        df["pq_time"] = 0
    if "prior_question_had_explanation" in df.columns:
        df["pq_exp"] = df["prior_question_had_explanation"].fillna(0).astype(int)
    else:
        df["pq_exp"] = 0

    FEAT = ["""

content = content.replace('    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes\n\n    FEAT = [', fe_resc_insertion)

# Update FEAT list for reschedule
r_feat_original = '"user_cat", "question_cat", "dataset_cat",'
r_feat_new = '"user_cat", "question_cat", "dataset_cat", "part", "pq_time", "pq_exp",'
content = content.replace(r_feat_original, r_feat_new)


# 3. Update train_motivation
mot_orig = """    num_cols = df.select_dtypes(include="number").columns.tolist()
    feat_cols = [c for c in num_cols if c.lower() not in {l.lower() for l in LEAK}
                 and "unnamed" not in c.lower()]

    df = df[df["stress_level"].notna()].copy()
    le = LabelEncoder()
    y  = le.fit_transform(df["stress_level"].astype(int))
    X  = df[feat_cols].fillna(0)"""

mot_new = """    feat_cols = [c for c in df.columns if c.lower() not in {l.lower() for l in LEAK} and "id" not in c.lower() and "unnamed" not in c.lower()]

    df = df[df["stress_level"].notna()].copy()
    le = LabelEncoder()
    y  = le.fit_transform(df["stress_level"].astype(int))
    X  = df[feat_cols].copy()
    
    # Categorical/Object to numeric
    for col in X.columns:
        if X[col].dtype == object:
            X[col] = LabelEncoder().fit_transform(X[col].astype(str))
    
    X = X.fillna(0)"""
content = content.replace(mot_orig, mot_new)


# 4. Update train_profiling
prof_orig = """    feat_cols = [
        "weekly_self_study_hours", "attendance_percentage_x", "class_participation",
        "total_score", "age", "study_hours", "attendance_percentage_y",
        "math_score", "science_score", "english_score", "overall_score",
    ]
    feat_cols = [c for c in feat_cols if c in df.columns]
    X = df[feat_cols].fillna(df[feat_cols].median())"""

prof_new = """    if 'highest_education' in df.columns:
        from sklearn.preprocessing import OrdinalEncoder
        feat_cols = ['code_module', 'code_presentation', 'gender', 'region', 'highest_education', 
                     'imd_band', 'age_band', 'num_of_prev_attempts', 'studied_credits', 'disability']
        X_raw = df[feat_cols].copy().astype(str)
        oe = OrdinalEncoder()
        X_encoded = oe.fit_transform(X_raw)
        X = pd.DataFrame(X_encoded, columns=feat_cols)
    else:
        feat_cols = [
            "weekly_self_study_hours", "attendance_percentage_x", "class_participation",
            "total_score", "age", "study_hours", "attendance_percentage_y",
            "math_score", "science_score", "english_score", "overall_score",
        ]
        feat_cols = [c for c in feat_cols if c in df.columns]
        X = df[feat_cols].fillna(df[feat_cols].median())"""
content = content.replace(prof_orig, prof_new)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("retrain_high_accuracy.py updated successfully!")
