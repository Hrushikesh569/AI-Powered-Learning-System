# Quick Start - Hierarchical Topics Implementation

## 🚀 What You Can Do Now

### 1. Upload a Syllabus (Auto-Creates Hierarchical Structure)

```bash
POST /api/v1/content/upload-schedule
{
  file: "YourSyllabus.pdf",
  subject: "Computer Networks",
  num_days: 30,
  hours_per_day: 2.0
}
```

**What happens automatically:**
- ✅ Extracts text from PDF
- ✅ Identifies all subjects (CN, DS, OS, etc.)
- ✅ Analyzes each subject with LLM
- ✅ **Creates ScheduledTopic records** (NEW!)
  - One record per topic
  - Organized by subject → unit → topic
  - Status: "pending"
  - Ready for scheduling

---

### 2. View Hierarchical Structure

```bash
GET /api/v1/content/files/{material_id}/topics-hierarchical
```

**Returns:**
```json
{
  "subjects": [
    {
      "subject": "Computer Networks",
      "subject_code": "CS301",
      "units": [
        {
          "unit_name": "UNIT-1",
          "topics": [
            {"id": 123, "topic_name": "OSI Model", "status": "pending"},
            {"id": 124, "topic_name": "Data Flow", "status": "pending"},
            ...
          ]
        }
      ]
    },
    {
      "subject": "Data Structures",
      "subject_code": "CS202",
      "units": [...]
    }
  ]
}
```

**Use this to:**
- Display organized topic list to user
- Group by subject and unit
- Show current status (pending/completed/rescheduled)

---

### 3. Mark Topic Complete

```bash
PATCH /api/v1/content/scheduled-topics/{topic_id}/complete
{
  "completion_notes": "Completed all exercises"
}
```

**What changes:**
- `status`: "pending" → "completed"
- `completed_date`: null → now
- `completion_notes`: Saved

**Track progress:** Query to see how many completed

---

### 4. Reschedule Topic

```bash
PATCH /api/v1/content/scheduled-topics/{topic_id}/reschedule
{
  "new_scheduled_date": "2026-03-20T10:00:00",
  "reason": "Exam took priority"
}
```

**What changes:**
- `status`: "pending" → "rescheduled"
- `scheduled_date`: new date
- `rescheduled_date`: now

**Prevents backlog:** Auto-rescheduled topics don't pile up

---

### 5. Query by Status

```bash
# Get all pending topics
GET /api/v1/content/scheduled-topics?status=pending

# Get all completed topics
GET /api/v1/content/scheduled-topics?status=completed

# Get topics for a specific file
GET /api/v1/content/scheduled-topics?material_id=11&status=pending
```

**Useful for:**
- Scheduler agent: Find topics to assign
- Progress agent: Track completed topics
- Reschedule agent: Find overdue topics

---

## 📊 Database Tables (Summary)

### ScheduledTopic (NEW)
```
id | user_id | material_id | subject | unit_name | topic_name | ...
---|---------|------------|---------|-----------|-----------|----
1  | 36      | 11         | CN      | UNIT-1    | OSI Model  | ...
2  | 36      | 11         | CN      | UNIT-1    | Data Flow  | ...
3  | 36      | 11         | DS      | UNIT-1    | Arrays     | ...
```

**Key fields:**
- `subject` + `unit_name` + `topic_name` = Hierarchical path
- `status` = "pending" | "completed" | "rescheduled" | "skipped"
- `estimated_hours` + `difficulty` = From LLM analysis
- `scheduled_date` = When to study (assigned by scheduler)
- `completed_date` = When actually studied
- `rescheduled_date` = When moved to new date

---

## 🔗 Integration Checklist

### Scheduler Agent
- [ ] Call `GET /scheduled-topics?status=pending` to get available topics
- [ ] Generate study plan based on estimated_hours and user availability
- [ ] Store plan in StudyPlan table with topic assignments
- [ ] UI displays scheduled_date for each topic

### Reschedule Agent
- [ ] Call `GET /scheduled-topics?status=pending` daily
- [ ] Find topics where `scheduled_date < now()`
- [ ] PATCH `/reschedule` to move to next available slot
- [ ] Prevents accumulating backlog

### Progress Agent
- [ ] Call `GET /scheduled-topics?status=completed` 
- [ ] Count completed topics vs. total
- [ ] Track completion rate over time
- [ ] Use completion_notes for insights

### Frontend UI
- [ ] Call `GET /files/{id}/topics-hierarchical` on load
- [ ] Display as tree: Subject > Unit > Topic
- [ ] Show status badge (pending/completed/rescheduled)
- [ ] Add buttons: "Mark Complete", "Reschedule"

---

## ✅ Verification Steps

### 1. Check table exists
```bash
docker exec 070a9348f848 python /app/test_scheduled_topics.py
# Output: ✓ ScheduledTopic table exists
```

### 2. Upload a file
```bash
curl -X POST -F "file=@syllabus.pdf" -F "subject=CN" \
  http://localhost:8000/api/v1/content/upload-schedule \
  -H "Authorization: Bearer {token}"
# Note material_id returned
```

### 3. Wait 30-60 seconds for extraction

### 4. Check hierarchical structure
```bash
curl -H "Authorization: Bearer {token}" \
  http://localhost:8000/api/v1/content/files/{material_id}/topics-hierarchical
# Should return subjects with units and topics
```

### 5. Try operations
```bash
# Get pending topics
curl "http://localhost:8000/api/v1/content/scheduled-topics?status=pending" \
  -H "Authorization: Bearer {token}"

# Mark first one complete
curl -X PATCH \
  -H "Authorization: Bearer {token}" \
  -d '{"completion_notes": "Test"}' \
  http://localhost:8000/api/v1/content/scheduled-topics/{first_topic_id}/complete

# Verify status changed
curl "http://localhost:8000/api/v1/content/scheduled-topics/{first_topic_id}" \
  -H "Authorization: Bearer {token}"
```

---

## 📚 Documentation Files

1. **HIERARCHICAL_STRUCTURE_GUIDE.md** - Complete API reference with examples
2. **IMPLEMENTATION_SUMMARY.md** - Technical implementation details
3. **VISUAL_REFERENCE.md** - Diagrams and workflows

---

## 🎯 Next Steps

1. **Test with next file upload** - Verify ScheduledTopic records are created
2. **Integrate scheduler agent** - Call endpoints to fetch/assign topics
3. **Update frontend** - Display hierarchical view and completion controls
4. **Connect reschedule agent** - Auto-reschedule overdue topics
5. **Enable progress tracking** - Query completed topics for insights

---

## ❓ Common Questions

**Q: Will existing uploaded files have ScheduledTopic records?**
A: No. Only NEW uploads will auto-create them. To backfill, manually trigger `POST /files/{id}/analyze`.

**Q: Can I modify a topic's details?**
A: Not via API yet. Currently: create on upload, update status/dates with patch endpoints.

**Q: What if I want to stop tracking a topic?**
A: Either mark as "skipped" (manual DB) or just ignore it in the schedule.

**Q: How does this affect existing topic lists?**
A: Fully backward compatible. `StudyMaterial.topics` still has flat list. `ScheduledTopic` is additional layer.

**Q: Can scheduler manually override rescheduled topics?**
A: Yes, by calling `/reschedule` again with a different date.

---

## 📞 Support

If endpoints return 404:
- Check user_id matches (security)
- Verify material_id exists
- Confirm status param is one of: pending, completed, rescheduled, skipped

If no topics appear:
- File may still be processing (check access logs)
- Try refreshing in 30-60 seconds
- Verify PDF wasn't corrupted during upload
