"""Bridge gestures to the game session; the graphics view knows no rules."""
import chess


def square_tuple(square):return (chess.square_file(square),chess.square_rank(square))


def square_index(square):return chess.square(*square) if square is not None else None


class RuleInput:
    managed_rendering=True

    def __init__(self,page):self.page=page

    @property
    def selected_square(self):
        session=self.page.session
        return square_tuple(session.bound_source) if session and session.running and session.bound_source is not None else None

    @property
    def allows_input(self):
        return self.page.session is not None and self.page.session.running and self.page.session.human_turn and self.page.dialog is None

    def press(self,square):
        if self.allows_input:self.page.session.touch(square_index(square))
        self.page.refresh_session()

    def request(self,intent):
        if not self.allows_input:return
        session=self.page.session
        attempt=session.try_move(square_index(intent.source),square_index(intent.target),expected_revision=session.revision)
        self.page.handle_attempt(attempt,intent)
