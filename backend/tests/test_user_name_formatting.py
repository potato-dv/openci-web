import unittest

from app.schemas.user import UserCreate


class UserNameFormattingTests(unittest.TestCase):
    def make_user(self, name: str) -> UserCreate:
        return UserCreate(
            name=name,
            email="agent@example.com",
            password="a sufficiently long password",
        )

    def test_name_is_trimmed_collapsed_and_title_cased(self):
        self.assertEqual(self.make_user("  jUAN   dELA   cRUZ ").name, "Juan Dela Cruz")

    def test_already_formatted_name_is_unchanged(self):
        self.assertEqual(self.make_user("Maria Santos").name, "Maria Santos")

    def test_whitespace_only_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_user("   ")


if __name__ == "__main__":
    unittest.main()
