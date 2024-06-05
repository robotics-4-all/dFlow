# how-to

This is the manual of the *dflow*  grammar.

### Entities

Entities are useful structured pieces of information inside a user message (e.g., names, cities, time expressions). They can be:
- *TE*: Trainable (custom) entities
- *PE*: Pretrained entities

The TE are defined in the `entity` block with their example phrases comma separated.
The PE are only defined in the intents.

```
entity
  Entity <name_1>
    example1,
    example2
  end
  Entity <name_2>
    another_example1,
    another_example2
  end
end
```

##### Example

```
entity
  Entity doctor
    "cardiologist",
    "dentist",
    "neurologist"
  end
end
```

### Synonyms

Synonyms map words to a value other than the literal text extracted. They can be used when there are multiple ways users refer to the same thing. Similarly, after defined, they are incorporated in the intent examples. All synonyms are defined in the `synonyms` block with their phrases comma separated.

```
synonyms
  Synonym <syn_name_1>
    example1,
    example2
  end
  Synonym <syn_name_2>
    another_example1,
    another_example2
  end
end
```

##### Example

```
synonyms
    Synonym date_period
        "day",
        "week",
        "month",
        "tomorrow",
        now
    end
end
```

### Services

External services are HTTP endpoints that can be used as part of the assistant's responses. Their URL and verb are defined globally in the `services` block, while their parameters are specified inside the dialogue section where they are called. The global parameters are four:
- verb: GET, POST or PUT
- host: the IP
- port: optional URL port
- path: optional URL path

```
eservices
    EServiceHTTP <name>
        verb: GET/POST/PUT
        host: <IP>
        port: <int>
        path: <path>
    end
end
```

##### Example

```
eservices
    EServiceHTTP weather_svc
        verb: GET
        host: 'r4a.issel.ee.auth.gr'
        port: 8080
        path: '/weather'
    end
end
```

### Global Slots

Global slots are variables that can be accessed and modified in a global scope. They are defined in the `gslots` block with their name, type and optionally their default value. They are comma separated.

```
gslots
    <slot_name>: <type> = <value>,
    <slot_name_2>: <type>
end
```

##### Example

```
gslots
    slotA: int = 10,
    slotB: str = "asdas"
end
```

### Triggers

A Trigger initializes a dialogue flow and is either a user expression, or so called *Intent*, or an external *Event*. Both are defined in the `triggers` block with their names and their data. Intents need *at least 2* training phrases comma separated and events need a URI from which they are triggered.

```
triggers
    Intent <intent_name>
        example_1,
        example_2
    end
    Event <event_name>
      <uri>
    end
end
```

#### Intent training phrases

An intent training phrase is a collection of (space separated) strings, synonyms and entities.
- strings need `"` in the start and end of the phrase,
- synonyms are referred with the *S* and their ID name: `S:syn_name_1`,
- trainable entities are referred with the *TE* and their ID name: `TE:name_2`,
- pretrained entities are referred with the *PE*, their category name and a few examples can be optionally given (it is advised to give at least one per category): `PE:PERSON['John','Mary']`

The pretrained entity categories are: `PERSON, NORP, FAC, ORG, GPE, LOC, PRODUCT, EVENT, WORK_OF_ART, LAW, LANGUAGE, DATE, TIME, PERCENT, MONEY, QUANTITY, ORDINAL, CARDINAL`.

##### Example

```
triggers
    Intent greet
        "hey",
        "hello",
        "hi",
        "good morning",
        "good evening",
        "hey there",
        "Hey",
        "Hi there",
    end
    Intent find_person
        "I want" TE:name "please",
        TE:name "please!",
        "I want to call" TE:name,
        "I want call" TE:name S:date_period,
        "call" TE:name "now",
        "I want to call" PE:PERSON "immediately",
        "call" PE:PERSON["John"] "now"
    end
    Event called_person
      '/bot/home/call'
    end
    Event reminder
      '/bot/home/reminders/remind_1'
    end
end
```

### Dialogues

Dialogues are conversational flows the assistant supports. They are sets of triggers and assistant responses in order and each response can be an *ActionGroup* or a *Form*.

#### ActionGroup

An ActionGroup is a collection of actions (line separated) is an assistant response that can either be:
- *SpeakAction*: states a specific text,
- *FireEventAction*: fires an Event,
- *SetGSlot*: sets a global slot with a particular value,
- *SetFSlot*: sets a form slot with a particular value,
- *RESTCallAction*: calls an HTTP endpoint

##### Environment properties

Environment properties are *user* or *system* variables or functions that can be used from the assistant during design and are computed at run time. These words are unique to the grammar and cannot be used as other IDs.

User properties are locally stored information about the user:
- NAME
- SURNAME
- AGE
- EMAIL
- PHONE
- CITY
- ADDRESS

System properties are functions that are called at run time:
- TIME
- LOCATION
- RANDOM_INT
- RANDOM_FLOAT

##### SpeakAction

The stated text can be a collection of strings, references to global or form slots, user or system properties.

- string: `'some text'`,
- reference to form slot: `<form_name>.<slot_name>` e.g., `AF1.slot1`
- reference to global slot: `<gslot_name>`
- user or system property: `<in_build_name>`

###### Example

`Speak('Hello' AF1.slot1 'how are you?')`

##### FireEventAction

Sends a message to a broker URI endpoint. The URI can be a TextStr, environment property, or slot reference, while the message can be of any type, all the above plus list or dictionary.

###### Example

`FireEvent('/test', ['a', 1, 'b','2'])`

##### SetFormSlot

Set a form slot with a specific value.

###### Example

`SetFSlot(form1.city_slot, "London")`

##### SetGlobalSlot

Set a form slot with a specific value.

###### Example

`SetGSlot(slotA, 10)`

##### RESTCallAction

Calls an HTTP endpoint that has been defined in the `services` block. The call has optional query, head, path and body parameters of any type. These dynamic params need to be separated with comma and another comma is needed in the end right before the closing parenthesis.

###### Example

`weather_svc(
    query=[city=[form1.city_slot[city]], time=form1.time_slot, user=USER:NAME],
    header=[city=form1.city_slot[city], time=form1.time_slot],
)`

#### Forms

A From is a conversational pattern to collect information and store it in form parameters or *slots* following business logic. Information can be collected via an *HRI*  interaction, in which the assistant collects the information from the user. It requests each slot using a specific text and extracts the data from the user expression. It can contain the entire processed text (the extract variable is not filled), an extracted entity, or a specific value set in case the user states a particular intent. The second choice is the *EServiceParamSource* interaction, in which the slot is filled with information received from an external service, that is defined above. Each slot is of one of the 6 types: `int`, `float`, `str`, `bool`, `list` or `dict`.

##### HRI

Collects information from the user by asking a question, processing the user expression and then if the particular information is given it is stored in the slot, else the assistant requests the slot again.

The information can be extracted from:
- The *entire* user expression <br>
`city_slot: str = HRI("For which city" USER:NAME "?")`
- A detected *entity* -> slot is given <br>
`<param_name>: <type> = HRI(<req_text>, [TE/PE: <entity_name>])` <br>
city_slot: str = HRI("For which city" USER:NAME "?", [PE:LOC])
- A detected *intent* -> slot is given a specific value <br>
`<param_name>: <type> = HRI(<req_text>, [intent_1: value_1])` <br>
`param: bool = HRI('yes/no', [affirm:True, deny:False])`



##### EServiceParamSource

Similar to RESTCallAction. It can also process the response as a dictionary by giving the keys full stop separated in the end of the line.

`weather_svc(
    query=[city=[form1.city_slot[city]], time=form1.time_slot, user=USER:NAME],
    header=[city=form1.city_slot[city], time=form1.time_slot],
)[weather.forecast]`

##### Example

```
dialogues
    Dialogue DialA
        on: external_1
        responses: answers
          Speak('Hello')
          Speak('Hey there')
    end

    Dialogue DialB
        on: find_doctor
        responses:
            Form AF1
                slot1: str = HRI('Give parameter 1', [PE:PERSON])
                slot2: str = HRI('Give parameter 2',
                    [find_doctor:True, external_1:False])
                slot3: str = HRI('Give parameter 3 you' AF1.slot1, [TE:Doctor])
            end,
            ActionGroup answers
              Speak('Hello' AF1.slot1 'how are you')
              FireEvent('/test', ['a', 1, 'b','2'])
            end
    end
end
```
