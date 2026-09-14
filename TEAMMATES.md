# Danh sách thành viên nhóm

**Repository:** [https://github.com/thangws4/K4-Day04-2A202602605](https://github.com/thangws4/K4-Day04-2A202602605)

| STT | Họ và tên | MSSV | GitHub Username | Email | Vai trò trong Lab |
|---|---|---|---|---|---|
| 1 | Nguyễn Đức Thắng (Nhóm trưởng) | 202602605 | thangws4 / thangnd11 | thangnguyen11112002@gmail.com | **Role A**: Prompt Architect & Lead (`system_prompt.md`, `version_log.csv`, merge PR) |
| 2 | Nguyễn Hải Long | 202602606 | long27112003 | longhello2003@gmail.com | **Role B**: Tool & Schema Engineer (`tools.yaml`, provider rate-limit resilience) |
| 3 | Tiền Dũng | 202602607 | tiendungtoandrew | tiendungtoandrew@gmail.com | **Role C**: Eval & Red-Team (`eval_group.json`, adversarial evaluation) |
| 4 | Trần Anh Quân | 202602608 | AnhQun18 | trananhquan20051812@gmail.com | **Role D**: UI & Report Coordinator (`app.py`, `ui_demo.html`, `REPORT.md`) |

---

### Phân công trách nhiệm & Đóng góp:
- **Nguyễn Đức Thắng (Role A):** Thiết kế cấu trúc `system_prompt.md`, quản lý version hashing, review và merge toàn bộ PR của các thành viên.
- **Nguyễn Hải Long (Role B):** Tối ưu hóa toàn bộ schema và mô tả trong `tools.yaml`, chuẩn hóa các enum/arguments, xử lý cơ chế retry và rate-limit cho Gemini API.
- **Tiền Dũng (Role C):** Thiết kế 10 test case nguyên bản cho bộ đánh giá nhóm (`data/eval_group.json` gồm 5 single-turn và 5 multi-turn), chạy thử nghiệm adversarial.
- **Trần Anh Quân (Role D):** Xây dựng ứng dụng Web Live Chat bằng Streamlit (`app.py`), giao diện demo `ui_demo.html`, phối hợp tổng hợp báo cáo `REPORT.md`.
