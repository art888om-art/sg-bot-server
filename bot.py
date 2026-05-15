    def _api_login(self):
        data = self._get_json_body()
        tg_id = str(data.get("tg_id", "")).strip()
        password = data.get("password", "")
        try:
            managers_ws = client.open_by_url(SHEET_URL).worksheet("Менеджеры")
            records = managers_ws.get_all_records()
            # Отладочный вывод: возвращаем заголовки и первую запись
            debug_info = {
                "headers": managers_ws.row_values(1),
                "first_record": records[0] if records else None,
                "input_tg_id": tg_id,
                "input_password": password
            }
            self._send_json({"ok": False, "error": "DEBUG", "debug": debug_info}, 200)
            return
        except Exception as e:
            logger.error(f"Login error: {e}")
            self.send_error(500)
