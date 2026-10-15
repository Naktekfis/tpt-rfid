# tpt-rfid Domain Language

**Student**:
A registered borrower with name, NIM, email, phone, optional photo, and one RFID card.
_Avoid_: user, member

**Tool**:
A workshop item with its own RFID tag; its status is `available` or `borrowed`.
_Avoid_: item, asset

**Transaction**:
One borrow of one Tool by one Student, closed when the Tool is returned. Keeps copies of the student and tool names.
_Avoid_: loan record, history entry

**RFID UID**:
The tag/card identifier read by the USB UHF reader (EPC as uppercase hex); unique across Students and across Tools.
_Avoid_: card number, tag ID

**Admin**:
Lab staff signed in with the admin PIN; can see borrowers, add tools, export history, and send reminder emails.
