from pdf_presenter.services.native_input import command_for_key


def test_native_shortcuts_keep_queue_navigation_and_number_entry_private():
    assert command_for_key(0x27) == "next"
    assert command_for_key(0x22, control=True) == "next_file"
    assert command_for_key(0x74, shift=True) == "start_current"
    assert command_for_key(0x35) == command_for_key(0x65) == "digit:5"
    assert command_for_key(0x0D) == "submit"
    assert command_for_key(0x0D, control=True) == "open_selected"
    assert command_for_key(0x73, alt=True) == ""
    assert command_for_key(0x4C, meta=True) == ""
    assert command_for_key(0x41) == ""
