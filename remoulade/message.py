# This file is a part of Remoulade.
#
# Copyright (C) 2017,2018 CLEARTYPE SRL <bogdan@cleartype.io>
#
# Remoulade is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# Remoulade is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import time
from typing import Any, Dict, Generic, TypeVar, cast

import attr

from remoulade.state import State

from .broker import get_broker
from .common import generate_unique_id
from .composition import pipeline
from .encoder import Encoder, JSONEncoder
from .errors import InvalidProgress
from .result import Result

#: The global encoder instance.
global_encoder = JSONEncoder()  # type: Encoder


def get_encoder() -> Encoder:
    """Get the global encoder object.

    Returns:
      Encoder
    """
    global global_encoder
    return global_encoder


def set_encoder(encoder: Encoder) -> None:
    """Set the global encoder object.

    Parameters:
      encoder(Encoder): The encoder instance to use when serializing
        messages.
    """
    global global_encoder
    global_encoder = encoder


ResultT = TypeVar("ResultT", bound=Result[Any], covariant=True)


@attr.s(frozen=True, slots=True, kw_only=True, auto_attribs=True)
class Message(Generic[ResultT]):
    """Encapsulates metadata about messages being sent to individual actors.

    Parameters:
      queue_name(str): The name of the queue the message belogns to.
      actor_name(str): The name of the actor that will receive the message.
      args(tuple): Positional arguments that are passed to the actor.
      kwargs(dict): Keyword arguments that are passed to the actor.
      options(dict): Arbitrary options passed to the broker and middleware.
      message_id(str): A globally-unique id assigned to the actor.
      message_timestamp(int): The UNIX timestamp in milliseconds
        representing when the message was first enqueued.
    """

    queue_name: str
    actor_name: str
    args: tuple = attr.field(converter=tuple)
    kwargs: Dict
    options: Dict[str, Any]
    message_id: str = attr.field(factory=generate_unique_id)
    message_timestamp: int = attr.field(factory=lambda: int(time.time() * 1000))

    def __or__(self, other) -> pipeline:
        """Combine this message into a pipeline with "other"."""
        return pipeline((self, other))

    def asdict(self):
        """Convert this message to a dictionary."""
        return attr.asdict(self, recurse=False)

    @classmethod
    def decode(cls, data):
        """Convert a bytestring to a message."""
        return cls(**global_encoder.decode(data))

    def encode(self):
        """Convert this message to a bytestring."""
        return global_encoder.encode(self.asdict())

    def copy(self, **attributes):
        """Create a copy of this message."""
        updated_options = attributes.pop("options", {})
        options = self.options.copy()
        options.update(updated_options)
        return attr.evolve(self, **attributes, options=options)

    def build(self, options: Dict[str, Any]):
        """Build message for pipeline"""
        return self.copy(options=options)

    def cancel(self) -> None:
        """Mark a message as canceled"""
        broker = get_broker()
        backend = broker.get_cancel_backend()
        backend.cancel([self.message_id])

    def set_progress(self, progress: float) -> None:
        """Set the progress of the message.
        progress(float) number between 0 and 1 inclusive

        :raises:
            InvalidProgress: when not( 0 <= progress <= 1)
        """
        if not (0 <= progress <= 1):
            raise InvalidProgress(f"Progress {progress} is not between 0 and 1.")

        broker = get_broker()
        backend = broker.get_state_backend()
        backend.set_state(State(self.message_id, progress=progress))

    @property
    def result(self) -> ResultT:
        return cast(ResultT, Result(message_id=self.message_id))

    def __str__(self) -> str:
        return f"{self.actor_name} / {self.message_id}"
