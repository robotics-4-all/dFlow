# dflow

A Domain-Specific Language for Task-based dialogue flows suitable for Virtual Assistants in smart environments.  

[Task-based FSM Presentation](https://docs.google.com/presentation/d/1-cS397zUys6AUH7NB00PnPVJY91_LgPzD6LdHc6AjxY/edit#slide=id.g1217cdb7144_0_0)

[System overview](https://docs.google.com/document/d/1jlFrizaDi1PD9Rtw-TwVXaGQYwpViTWV3sUK8sJBx-c/edit)

# Metamodel

The metamodel of the DSL, defines the concepts of the language.

![Metamodel](./assets/metamodel.png)


# Similar Work Resources

R&D:

- [A Model-based Chatbot Generation Approach to talk with Open Data Sources](https://modeling-languages.com/a-model-based-chatbot-generation-approach-to-talk-with-open-data-sources/)
- [Multi-Platform Chatbot Modeling and Deployment with the Xatkit Framework](https://modeling-languages.com/multi-platform-chatbot-modeling-deployment-xatkit/)
- [New Chatbot DSL based on state machines – Xatkit’s language is now more powerful than ever!](https://xatkit.com/chatbot-dsl-state-machines-xatkit-language/)
- [Talking to Dimensional Data Through Chatbots](https://modeling-languages.com/talking-to-dimensional-data-with-chatbots-and-nlp/)
- [Towards conversational syntax for DSLs using chatbots - miso](https://www.miso.es/pubs/ECMFA-2019.pdf)
- [Model-driven chatbot development](https://miso.es/pubs/ER20.pdf)

Platforms:

- [JAICP](https://just-ai.com/)
- [The building blocks for building chatbots](https://botpress.com/)


# TOC

# Overview

# User Guide

## Installation

Download this repository and simply install using pip package manager.

```
git clone https://github.com/robotics-4-all/dFlow
cd dFlow
pip install .
```

## Generate model

To generate a metamodel from `metamodel.dflow` file to a complete Rasa model, run the following.

```
textx generate metamodel.dflow --target rasa -o output_path (Default: ./gen/)
```

## Grammar

The grammar of the language has four main attributes:

- Entities
- Synonyms
- Triggers
- Dialogues

### Entities

**Entities** are structured pieces of information inside a user message. They can be real-world objects, such as a person, location, organization, product, etc. In those generic cases, there are existing *Pre-trained models* that can be used to extract entities from text and the Pre-trained Entity is defined inside the intent examples. The supported categories can be found in [spacy](https://spacy.io/models), from where the relevant model has to be installed.

In cases where the entity is domain or use-case specific such below, examples need to be given to train a new entity extractor. This is the case of a *Trainable* Entity, which is first defined and then included in the intents section.

```
Entity: TrainableEntity | PretrainedEntity;

TrainableEntity:
    'Entity' name=ID
        words+=Word[',']
    'end'
;

PretrainedEntity:
    'PERSON'        |
    'NORP'          |
    'FAC'           |
    'ORG'           |
    'GPE'           |
    'LOC'           |
    'PRODUCT'       |
    'EVENT'         |
    'WORK_OF_ART'   |
    'LAW'           |
    'LANGUAGE'      |
    'DATE'          |
    'TIME'          |
    'PERCENT'       |
    'MONEY'         |
    'QUANTITY'      |
    'ORDINAL'       |
    'CARDINAL'
;
```

###### Example

```
entities
    Entity Doctor
        cardiologist,
        dentist,
        doc
    end
end
```

### Synonyms

**Synonyms** map extracted entities to a value other than the literal text extracted. They can be used when there are multiple ways users refer to the same thing. Similarly, after defined, they are incorporated in the intent examples.

```
Synonym:
    'Synonym' name=ID
        words+=Word[',']
    'end'
;
```

###### Example

```
synonyms
    Synonym date_period
        day,
        week,
        month,
        tomorrow,
        now
    end
end
```

### Triggers

A **Trigger** initializes a dialogue flow. It can be a user expression or *Intent* or an external *Event*.

`Trigger: Intent | Event;`

#### Intents

For an assistant to recognize what a user is saying no matter how the user phrases their message, we need to provide example messages the assistant can learn from. We group these examples according to the idea or the goal the message is expressing, which is called the **Intent**. Each intent has a few examples that consist of strings, references to Trainable Entities (TE), to Synonyms (S), and to Pretrained Entities (PE). Regarding the PEs, users can also give example words inside the brackets apart from the entity category (e.g., `PE:PERSON["John"]`).   

```
Intent:
    'Intent' name=ID
        phrases+=IntentPhraseComplex[',']
    'end'
;

IntentPhraseComplex: phrases+=IntentPhrase;

IntentPhrase: IntentPhraseStr | IntentPhraseTE | IntentPhraseSynonym | IntentPhrasePE;

IntentPhraseStr: STRING;

IntentPhraseTE: 'TE:' trainable=[TrainableEntity|FQN];

IntentPhrasePE: 'PE:' pretrained=[PretrainedEntity|FQN] ('[' refPreValues*=STRING[','] ']')?;

IntentPhraseSynonym: 'S:' synonym=[Synonym|FQN];
```
###### Example

In the code block below we have added a simple intent called *greet*, which contains example messages like "Hi", "Hey" and "Good morning", and a more complex *find_person* that uses all the possible references.

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
end
```

#### Events

**Events** are external triggers, such as IoT events, notifications or reminders. An event needs its name and the URI from which it is triggered.

```
Event:
    'Event' name=ID
        uri=STRING
    'end'
;
```

###### Example

```
Event external_1
    "bot/event/external_1"
end
```

### Dialogues

**Dialogues** depict the conversational flows the assistant will support. They are sets of triggers and assistant responses in order. Each response can be an *Action* or a *Form*.

```
Dialogue:
    'Dialogue' name=ID
        'on:' onTrigger=[Trigger|FQN]
        'responses:' responses+=Response[',']
    'end'
;

Response: Action | Form;
```

###### Example

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
        responses: Form AF1
            Param1: int[text] = HRI('Give parameter 1')
            Param2: bool[find_doctor:True, external_1:False] = HRI('Give parameter 2')
            Param3: str[Doctor] = HRI('Give parameter 3 you')
        end,
        answers_2
          Speak('Hello')
    end
end
```

#### Actions

An action is an assistant response that can either:
- Speak a specific text
- Fire an Event, or
- Call an HTTP endpoint

```
Action: name=ID actions+=ActionTypes;
ActionTypes: SpeakAction | FireEventAction | HTTPCallAction;

SpeakAction:
    'Speak' '(' text=STRING ')'
;

FireEventAction:
    'FireEvent' '(' uri=STRING ',' msg=STRING ')'
;

HTTPCallAction:
    'RESTCall' '('
        host=STRING ','
        port=INT ','
        path=STRING ','
        '[' query_params*=STRING[','] ']' ','
        '[' path_params*=STRING[','] ']' ','
        '[' body_params*=STRING[','] ']' ','
    ')'
;
```

#### Forms

A From is a conversational pattern to collect information and store them in form parameters or *slots* following business logic. The assistant requests each slot using a specific text and extracts information from the user expression. Each slot has one of the 4 types (int, float, text, bool) and is filled from the processed text, from an extracted entity, or with a specific value if user stated a particular intent.

```
Form:
    'Form' name=ID
        params+=FormParameter
    'end'
;

FormParameter:
    name=ID ':' type=ParameterType '[' extract+=ExtractionSource[','] ']' '=' source=ParameterSource
;

ParameterSource: HRIParamResource;

HRIParamResource:
    'HRI' '(' ask_slot=STRING ')'
;

ParameterType: 'int' | 'float' | 'str' | 'bool';
ParameterDefault: STRING | INT | FLOAT | BOOL;

ExtractionSource: FromText | FromIntent | FromEntity;

FromText: 'text';
FromIntent: intent=[Trigger] ':' value=ParameterDefault;
FromEntity: entity=[Entity];
```

### Examples

Several examples can be found [here](./examples/).
