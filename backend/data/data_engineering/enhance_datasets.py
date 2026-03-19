import os
import glob
import pandas as pd
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(ROOT, "raw")
FINAL_DIR = os.path.join(ROOT, "final_training")
os.makedirs(FINAL_DIR, exist_ok=True)

def find_file(name):
    for root, dirs, files in os.walk(RAW_DIR):
        if name in files:
            return os.path.join(root, name)
    return None

def build_progress_and_reschedule():
    print("Building Progress and Reschedule from Riiid...")
    train_path = find_file("train.csv")
    questions_path = find_file("questions.csv")
    
    if not train_path or not questions_path:
        print("Riiid data not found. Skipping.")
        return

    qdf = pd.read_csv(questions_path)
    # create mapping
    qmap = qdf.set_index("question_id")[["part", "tags", "correct_answer"]]
    
    # Read a chunk from train.csv (e.g. 500k rows)
    chunk = pd.read_csv(train_path, nrows=500000)
    chunk = chunk[chunk['content_type_id'] == 0].copy()
    chunk = chunk.rename(columns={'content_id': 'question_id', 'answered_correctly': 'correct'})
    
    # Join question metadata
    meta = qmap.reindex(chunk['question_id'].values).reset_index(drop=True)
    meta.index = chunk.index
    df = pd.concat([chunk, meta], axis=1)
    
    # Convert timestamp to real datetime (assuming timestamp is milliseconds from start of user interaction)
    # We will just map it to an arbitrary starting date plus milliseconds for actual sequence behavior
    base_time = pd.to_datetime('2023-01-01')
    df['timestamp_parsed'] = base_time + pd.to_timedelta(df['timestamp'], unit='ms')
    df['user_id'] = df['user_id'].astype(int)
    
    df = df.sort_values(['user_id', 'timestamp_parsed']).reset_index(drop=True)
    
    # Keep columns for Progress
    progress_cols = ['user_id', 'question_id', 'timestamp', 'timestamp_parsed', 'correct', 'part', 'tags', 'prior_question_elapsed_time', 'prior_question_had_explanation']
    prog_df = df[progress_cols].copy()
    prog_df.to_csv(os.path.join(FINAL_DIR, "progress_training.csv"), index=False)
    print(f"  -> progress_training.csv ({len(prog_df)} rows) with rich columns")
    
    # Reschedule: calculate real delta_s
    prog_df['next_ts_parsed'] = prog_df.groupby('user_id')['timestamp_parsed'].shift(-1)
    # delta_s in seconds
    prog_df['delta_s'] = (prog_df['next_ts_parsed'] - prog_df['timestamp_parsed']).dt.total_seconds()
    
    # Filter valid reschedules
    resched = prog_df.dropna(subset=['delta_s', 'correct', 'part'])
    resched = resched[resched['delta_s'] > 0]
    resched.to_csv(os.path.join(FINAL_DIR, "reschedule_training.csv"), index=False)
    print(f"  -> reschedule_training.csv ({len(resched)} rows) with delta_s")

def build_motivation():
    print("Building Motivation from Clean Stress level dataset...")
    stress_file = find_file("StressLevelDataset.csv")
    if stress_file:
        df = pd.read_csv(stress_file)
        df.to_csv(os.path.join(FINAL_DIR, "motivation_training.csv"), index=False)
        print(f"  -> motivation_training.csv ({len(df)} rows)")
    else:
        print("StressLevelDataset.csv not found.")

def build_profiling():
    print("Building Profiling from Student Performance and OULAD...")
    # Math
    mat_file = find_file("student-mat.csv")
    mat_df = pd.DataFrame()
    if mat_file:
        mat_df = pd.read_csv(mat_file, sep=';')
        
    # OULAD
    oulad_file = find_file("studentInfo.csv")
    oulad_df = pd.DataFrame()
    if oulad_file:
        oulad_df = pd.read_csv(oulad_file)
        
    # We will save both to separate profiling outputs or merge them conceptually.
    # Since Profiling is clustering, we can just use the rich OULAD dataset.
    if not oulad_df.empty:
        # Save OULAD as profiling (32k rows)
        oulad_df = oulad_df.rename(columns={'id_student': 'user_id'})
        oulad_df.to_csv(os.path.join(FINAL_DIR, "profiling_training.csv"), index=False)
        print(f"  -> profiling_training.csv (from OULAD, {len(oulad_df)} rows)")
    elif not mat_df.empty:
        mat_df['user_id'] = range(len(mat_df))
        mat_df.to_csv(os.path.join(FINAL_DIR, "profiling_training.csv"), index=False)
        print(f"  -> profiling_training.csv (from student-mat, {len(mat_df)} rows)")
    else:
        print("No profiling data found.")

if __name__ == "__main__":
    print("ENHANCING DATASETS WITH RICH RAW FILES...")
    build_progress_and_reschedule()
    build_motivation()
    build_profiling()
    print("DONE.")
