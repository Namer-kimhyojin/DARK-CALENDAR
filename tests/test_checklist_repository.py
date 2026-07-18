from calendar_app.infrastructure.db import checklist_template_repo as checklist_repo
from tests.support import TemporaryDatabaseTestCase


class ChecklistRepositoryTests(TemporaryDatabaseTestCase):
    def test_template_and_item_crud_roundtrip(self):
        template_id = checklist_repo.create_checklist_template(
            name="월간 결산 업무",
            description="마감 체크리스트",
            category="common",
            checklist_type="process",
        )

        self.assertIsNotNone(template_id)

        template = checklist_repo.get_checklist_template(template_id)
        self.assertEqual(template["name"], "월간 결산 업무")
        self.assertEqual(template["checklist_type"], "process")

        first_item_id = checklist_repo.create_checklist_item(template_id, "자료 수집", item_order=0)
        second_item_id = checklist_repo.create_checklist_item(
            template_id, "최종 검토", item_order=1
        )

        self.assertIsNotNone(first_item_id)
        self.assertIsNotNone(second_item_id)

        items = checklist_repo.get_checklist_items(template_id)
        self.assertEqual([item["item_text"] for item in items], ["자료 수집", "최종 검토"])

        self.assertTrue(
            checklist_repo.update_checklist_template(template_id, {"name": "월말 결산 업무"})
        )
        self.assertTrue(
            checklist_repo.update_checklist_item(first_item_id, {"item_text": "결산 자료 수집"})
        )
        self.assertTrue(
            checklist_repo.reorder_checklist_items(template_id, [second_item_id, first_item_id])
        )

        updated_template = checklist_repo.get_checklist_template(template_id)
        updated_items = checklist_repo.get_checklist_items(template_id)

        self.assertEqual(updated_template["name"], "월말 결산 업무")
        self.assertEqual([item["id"] for item in updated_items], [second_item_id, first_item_id])
        self.assertEqual(updated_items[1]["item_text"], "결산 자료 수집")

        self.assertTrue(checklist_repo.toggle_checklist_template_active(template_id))
        active_templates = checklist_repo.get_all_checklist_templates(active_only=True)
        self.assertEqual(active_templates, [])

        self.assertTrue(checklist_repo.delete_checklist_template(template_id))
        self.assertIsNone(checklist_repo.get_checklist_template(template_id))

    def test_duplicate_checklist_template_copies_items_in_order(self):
        template_id = checklist_repo.create_checklist_template(
            name="배포 점검",
            description="릴리스 전 확인",
            category="release",
            checklist_type="process",
        )
        checklist_repo.create_checklist_item(
            template_id,
            "백업 확인",
            item_description="DB 백업 완료 여부",
            item_order=0,
            is_required=1,
        )
        checklist_repo.create_checklist_item(template_id, "릴리스 노트 확인", item_order=1)

        copied_id = checklist_repo.duplicate_checklist_template(template_id, "배포 점검 복사본")

        self.assertIsNotNone(copied_id)
        copied_template = checklist_repo.get_checklist_template(copied_id)
        copied_items = checklist_repo.get_checklist_items(copied_id)
        self.assertEqual("배포 점검 복사본", copied_template["name"])
        self.assertEqual("process", copied_template["checklist_type"])
        self.assertEqual(
            ["백업 확인", "릴리스 노트 확인"], [item["item_text"] for item in copied_items]
        )
        self.assertEqual([0, 1], [item["item_order"] for item in copied_items])
        self.assertEqual(1, copied_items[0]["is_required"])
