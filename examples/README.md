## Examples

### simple

A simple example to check model grammar. It contains one entity, one synonym, one intent, one event (2 triggers in total), and two dialogues. The first is triggered from the `find_doctor` intent and initiates a form with 3 slots and one speak action in the end. The second is triggered from the `external_1` event and initiates a form with 2 slots, and after they are filled, one speak action and one service call are executed.

### weather

This example is a basic *get weather report*, where the user requests a weather forecast using the preferred time and location and receives an answer from a particular weather API service. Th `ask_weather` intent is defined using a few examples that may or may not contain a pretrained LOC or TIME entity or both. One dialogue exists with is triggered from the intent and starts a form that has to collect a place and a time slot, mapped with the two pretrained entities, and an answer slot that is the response from the weather API service. Finally, a speak action is executed with the appropriate message.


### profile

This is a *profile filling* example, in which the user states his/her name and age and is then greeted from the assistant. One intent is defined that triggers a form with two slots, name and age, the first mapped with a pretrained entity while the second is extracted from the text. Finally, a speak action is executed that greets the user.
