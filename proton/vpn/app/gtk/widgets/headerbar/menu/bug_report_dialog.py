"""
Issue report module.


Copyright (c) 2023 Proton AG

This file is part of Proton VPN.

Proton VPN is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Proton VPN is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ProtonVPN.  If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from typing import TYPE_CHECKING, Optional
from gi.repository import Gtk, GLib, Gio
from proton.vpn.app.gtk import __version__
from proton.vpn import logging
from proton.vpn.app.gtk.utils.safe_signal_connect import safe_signal_connect
from proton.vpn.app.gtk.widgets.main.notification_bar import NotificationBar

if TYPE_CHECKING:
    from proton.vpn.app.gtk.controller import Controller
    from proton.vpn.app.gtk.app import MainWindow

logger = logging.getLogger(__name__)
UNEXPECTED_SUBMISSION_ERRORS = (RuntimeError, ValueError, TypeError, OSError)


class BugReportDialog(Gtk.Dialog):  # pylint: disable=too-many-instance-attributes
    """Widget used to compose issue reports for this community build."""
    WIDTH = 400
    HEIGHT = 300
    EMAIL_REGEX = re.compile(
        r'[^@\s]+@[^@\s]{2,}\.[^@\s\.-]{2,}'
    )
    BUG_REPORT_RECIPIENT = "libertypo@proton.me"
    BUG_REPORT_SENDING_MESSAGE = "Opening your email client..."
    BUG_REPORT_SUCCESS_MESSAGE = "Email draft opened"
    BUG_REPORT_UNEXPECTED_ERROR_MESSAGE = "Something went wrong. " \
                                          "Please send your report manually to:\n" \
                                          "libertypo@proton.me"
    BUG_REPORT_TITLE = "Community Linux App Report"
    BUG_REPORT_CLIENT = "Community Linux GUI"
    BUG_REPORT_VERSION = __version__
    BUG_REPORT_DESCRIPTION_MIN_CHARACTERS = 50

    def __init__(
        self, controller: Controller, main_window: MainWindow,
        notification_bar: Optional[NotificationBar] = None
    ):
        super().__init__()
        self.set_name("bug-report-dialog")
        self._controller = controller
        self._main_window = main_window
        self.notification_bar = notification_bar or NotificationBar()

        self.set_title("Report an Issue (Community Build)")
        self.set_default_size(BugReportDialog.WIDTH, BugReportDialog.HEIGHT)

        self.cancel_button = self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.submit_button = self.add_button("_Submit", Gtk.ResponseType.OK)

        self.cancel_button.add_css_class("danger")
        self.submit_button.add_css_class("primary")

        safe_signal_connect(self, "response", self._on_response)

        self._generate_fields()
        self.submit_button.set_sensitive(False)

    @property
    def status_label(self) -> str:
        """Returns the current message of the notification bar."""
        return self.notification_bar.current_message

    def _on_response(self, _: BugReportDialog, response: Gtk.ResponseType):
        """Upon any of the button being clicked in the dialog,
        it's responde is evaluated.
        """
        if response != Gtk.ResponseType.OK:
            self.close()
            return

        # Time here has to be long to account for network issues or when API is not
        # reacheable.
        self.notification_bar.show_info_message(self.BUG_REPORT_SENDING_MESSAGE, 60000)
        GLib.idle_add(self._submit_bug_report)

        # Prevent closing until mail client launch is attempted.
        self.stop_emission_by_name("response")

    def _submit_bug_report(self):
        username = self.username_entry.get_text().strip()
        user_email = self.email_entry.get_text().strip()
        description = self.description_buffer.get_text(
            self.description_buffer.get_start_iter(),
            self.description_buffer.get_end_iter(),
            True
        )

        logs_hint = ""
        if self.send_logs_checkbox.get_active():
            logs_hint = (
                "\n\nLogs were requested in the UI but are not attached automatically."
                " Please attach relevant files manually if needed."
                "\nApp logs: ~/.cache/Proton/VPN/logs/"
            )

        body = (
            "This report is for a community-modified build and is not endorsed by Proton AG.\n\n"
            f"Username: {username}\n"
            f"Contact email: {user_email}\n"
            f"App version: {self.BUG_REPORT_VERSION}\n"
            f"Client: {self.BUG_REPORT_CLIENT}\n\n"
            "Description:\n"
            f"{description}"
            f"{logs_hint}"
        )

        mailto_uri = (
            f"mailto:{self.BUG_REPORT_RECIPIENT}"
            f"?subject={quote(self.BUG_REPORT_TITLE)}"
            f"&body={quote(body)}"
        )

        self._disable_form()
        try:
            Gio.AppInfo.launch_default_for_uri(mailto_uri, None)
        except (GLib.Error, *UNEXPECTED_SUBMISSION_ERRORS):
            self.notification_bar.show_error_message(
                self.BUG_REPORT_UNEXPECTED_ERROR_MESSAGE
            )
            self._enable_form()
            logger.exception("Unable to open email client for bug report submission.")
        else:
            self._main_window.main_widget.notifications.show_success_message(
                self.BUG_REPORT_SUCCESS_MESSAGE
            )
            self.close()

        return False

    def _disable_form(self):
        self.username_entry.set_sensitive(False)
        self.email_entry.set_sensitive(False)
        self.description_textview.set_sensitive(False)
        self.send_logs_checkbox.set_sensitive(False)
        self.submit_button.set_sensitive(False)

    def _enable_form(self):
        self.username_entry.set_sensitive(True)
        self.email_entry.set_sensitive(True)
        self.description_textview.set_sensitive(True)
        self.send_logs_checkbox.set_sensitive(True)
        if self._can_user_submit_form:
            self.submit_button.set_sensitive(True)

    def _on_entry_changed(self, _: Gtk.Widget):
        self.submit_button.set_sensitive(self._can_user_submit_form)

    @property
    def _can_user_submit_form(self) -> bool:
        is_username_provided = len(self.username_entry.get_text().strip()) > 0
        is_email_provided = re.fullmatch(
            self.EMAIL_REGEX, self.email_entry.get_text()
        )
        is_description_provided = len(self.description_buffer.get_text(
            self.description_buffer.get_start_iter(),
            self.description_buffer.get_end_iter(),
            True
        )) > BugReportDialog.BUG_REPORT_DESCRIPTION_MIN_CHARACTERS

        return bool(
            is_username_provided
            and is_email_provided
            and is_description_provided
        )

    def _generate_fields(self):  # pylint: disable=too-many-statements
        """Generates the necessary fields for the report."""
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        layout.set_margin_top(0)
        layout.set_margin_bottom(0)
        layout.set_margin_start(0)
        layout.set_margin_end(0)
        layout.append(self.notification_bar)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        content.set_name("bug-report-content")
        layout.append(content)

        username_label = Gtk.Label(label="Username")
        username_label.set_halign(Gtk.Align.START)

        self.username_entry = Gtk.Entry()
        self.username_entry.set_property("margin-bottom", 10)
        self.username_entry.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        self.username_entry.set_name("username")
        content.append(username_label)
        content.append(self.username_entry)

        email_label = Gtk.Label(label="Email")
        email_label.set_halign(Gtk.Align.START)

        self.email_entry = Gtk.Entry()
        self.email_entry.set_property("margin-bottom", 10)
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.email_entry.set_name("email")
        content.append(email_label)
        content.append(self.email_entry)

        min_characters = BugReportDialog.BUG_REPORT_DESCRIPTION_MIN_CHARACTERS
        description_label = Gtk.Label(
            label=f"Description (minimum {min_characters} characters)"
        )

        description_label.set_halign(Gtk.Align.START)
        # Has to have min 50 chars
        self.description_buffer = Gtk.TextBuffer()
        self.description_textview = Gtk.TextView.new_with_buffer(
            self.description_buffer
        )
        self.description_textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.description_textview.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        self.description_textview.set_justification(Gtk.Justification.FILL)
        self.description_textview.set_name("description")
        scrolled_window_textview = Gtk.ScrolledWindow()
        scrolled_window_textview.set_property("margin-bottom", 10)
        scrolled_window_textview.set_min_content_height(100)
        scrolled_window_textview.set_child(self.description_textview)
        content.append(description_label)
        content.append(scrolled_window_textview)

        self.send_logs_checkbox = Gtk.CheckButton.new_with_label(
            "I will attach logs manually if requested"
        )
        self.send_logs_checkbox.set_active(False)
        self.send_logs_checkbox.set_name("send_logs")
        content.append(self.send_logs_checkbox)

        content_area = self.get_content_area()
        content_area.append(layout)
        content_area.set_margin_top(0)
        content_area.set_margin_bottom(0)
        content_area.set_margin_start(0)
        content_area.set_margin_end(0)
        content_area.set_spacing(20)

        safe_signal_connect(
            self.username_entry, "changed", self._on_entry_changed
        )
        safe_signal_connect(
            self.email_entry, "changed", self._on_entry_changed
        )
        safe_signal_connect(
            self.description_buffer, "changed", self._on_entry_changed
        )

    def get_submit_button(self):
        """Returns the Submit button."""
        return self.submit_button

    def click_on_submit_button(self):
        """Clicks the Submit button."""
        self.submit_button.emit("clicked")
