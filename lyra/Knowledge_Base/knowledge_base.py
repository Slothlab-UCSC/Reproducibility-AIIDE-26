import os, random, json
from typing import Dict, List, Optional

class KnowledgeBase:
    def __init__(self, path, load_from_disk=True):
        self.path = path
        print(path)
        self.kb: Dict[str, Topic] = {}

        if not os.path.isdir(self.path):
            os.makedirs(self.path, exist_ok=True)

        if load_from_disk:
            print("loading from disk")
            self.load_topics_from_disk()

    def load_topics_from_disk(self):
        for entry in os.listdir(self.path):
            topic_path = os.path.join(self.path, entry)
            if not os.path.isdir(topic_path):
                continue
            print(topic_path)
            self.kb[entry] = Topic(entry, topic_path, load_from_disk=True)

    def get_topics(self):
        return list(self.kb.keys())

    def get_topic(self, topic):
        return self.kb.get(topic)

    def get_knowledge_by_topic(self, topic, content_only=True):
        t = self.kb.get(topic)
        if not t:
            return [] if content_only else None
        return t.all_objects() if content_only else t

    def get_rand_discussion_obj(self):
        if not self.kb:
            return None
        topic = random.choice(list(self.kb.values()))
        return topic.get_random_object()

    def get_rand_obj_from_topic(self, topic):
        t = self.kb.get(topic)
        return t.get_random_object() if t else None

    def __contains__(self, obj):
        t = self.kb.get(obj.topic)
        if not t:
            return False
        return obj in t

    def learn_ood(self, obj) -> None:
        """
        Add or update an ObjectOfDiscussion in this agent KB.

        JSON layout (per topic, e.g. Villager.json):

        {
        "topic": "Villager",
        "sources": {
            "Block Chronicle": [
            { ... work 1 ... },
            { ... work 2 ... }
            ],
            "agent_left_high_uncertainty": [
            { ... work posted by that agent ... }
            ]
        }
        }
        """
        # print(obj)

        topic = obj.topic

        # Ensure in-memory Topic exists (agent KB; no disk load)
        if topic not in self.kb:
            self.kb[topic] = Topic(topic=topic, path=None, load_from_disk=False)

        # Add to in-memory Topic
        self.kb[topic].add_obj(obj)

        # Path to this agent's topic JSON (e.g. agent_X/Villager.json)
        json_path = os.path.join(self.path, f"{topic}.json")

        # Load existing JSON, or start fresh
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"topic": topic, "sources": {}}

        # Which "source bucket" does this work belong to?
        # For news outlets, this is the publisher name.
        # For agents-as-sources, set obj.publisher = agent name.
        source_name = obj.publisher or "Unknown"

        # Ensure this source has a list
        sources = data.setdefault("sources", {})
        works_list = sources.setdefault(source_name, [])

        # Build record for this specific work
        record = {
            "name": obj.name,
            "publisher": obj.publisher,
            "source_type": obj.source_type,
            "attitude": obj.attitude,
            "source_bias": obj.rating,
            "content": obj.content,
            "agent_opinion": getattr(obj, "agent_opinion", None),
        }

        # Update-or-append within THIS source's list
        replaced = False
        for existing in works_list:
            if existing.get("name") == obj.name:
                existing.update(record)
                replaced = True
                break

        if not replaced:
            works_list.append(record)

        # Write back JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
    
class Topic:
    def __init__(self, topic, path, load_from_disk=True):
        self.topic = topic
        self.path = path
        self.objs: List[ObjectOfDiscussion] = []
        self.rating = 0.0

        # print(path)
        if load_from_disk and self.path is not None and os.path.isdir(self.path):
            self.load_from_disk()

    def load_from_disk(self):
        # self.path is something like: "Knowledge_Base/Master_KB/Villager"
        works_path = os.path.join(self.path, f"{self.topic}.json")
        if not os.path.isfile(works_path):
            return  # no JSON for this topic

        with open(works_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        sources = data.get("Sources", [])
        for src in sources:
            publisher = src.get("Publisher", "Unknown Publisher")
            default_bias = float(src.get("Source_Bias", 0.0))
            works = src.get("Works", [])

            for w in works:
                name = w.get("Source_Name", "Unknown")
                source_type = w.get("Source_Type", "")
                attitude = float(w.get("Attitude", 0.0))
                rating = float(w.get("Source_Bias", default_bias))
                content = w.get("Description", "")

                obj = ObjectOfDiscussion(
                    name=name,
                    topic=self.topic,
                    publisher=publisher,
                    source_type=source_type,
                    attitude=attitude,
                    rating=rating,
                    content=content,
                )
                self.add_obj(obj)

            # update mean rating
        if self.objs:
            self.rating = sum(o.rating for o in self.objs) / len(self.objs)
        else:
            self.rating = 0.0

    def add_obj(self, obj):
        self.objs.append(obj)
        self._update_rating()

    def _update_rating(self):
        if self.objs:
            self.rating = sum(o.rating for o in self.objs) / len(self.objs)
        else:
            self.rating = 0.0

    def __contains__(self, obj):
        return any(o.name == obj.name for o in self.objs)

    def all_objects(self):
        return list(self.objs)

    def get_random_object(self):
        return random.choice(self.objs) if self.objs else None
    
        
        
class ObjectOfDiscussion:
    def __init__(
        self,
        name: str,
        topic: str,
        publisher: Optional[str] = None,
        source_type: str = "",
        attitude: float = 0.0,
        rating: float = 0.0,
        content: str = "",
        path: Optional[str] = None,
    ):

        self.name = name
        self.topic = topic
        self.publisher = publisher
        self.source_type = source_type
        self.attitude = float(attitude)
        self.rating = float(rating)
        self.content = content
        self.path = path
        self.agent_opinion: Optional[float] = None
        

    def __repr__(self):
        return f"ObjectOfDiscussion(name={self.name!r}, publisher={self.publisher!r}, rating={self.rating})"

    
    def __str__(self):
        return f"{self.name} (publisher={self.publisher}, rating={self.rating})"
    

if __name__ == "__main__":
    kb = KnowledgeBase("Knowledge Base/Master_KB")
    
    
    print(kb.get_knowledge_by_topic("Abortion"))
    print(kb.get_knowledge_by_topic("Abortion", True))
    print(kb.get_knowledge_by_topic("Fake news"))
    print(kb.get_knowledge_by_topic("Fake news", True))