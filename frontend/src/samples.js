// Demo images served from public/samples/ (COCO val2017; see backend/samples/ground_truth.json)
export const SAMPLES = [
  { file: '01_bedroom_empty.jpg', label: 'Empty bedroom', people: 0 },
  { file: '02_garage_cat_empty.jpg', label: 'Garage (cat)', people: 0 },
  { file: '03_living_room_gaming.jpg', label: 'Living room', people: 3 },
  { file: '04_baseball_catcher.jpg', label: 'Catcher', people: 1 },
  { file: '05_prom_couple.jpg', label: 'Couple', people: 2 },
  { file: '06_bikes_path.jpg', label: 'Bike path', people: 2 },
  { file: '07_street_crossing.jpg', label: 'Street crossing', people: 4 },
  { file: '08_street_statues.jpg', label: 'Statues', people: 4 },
  { file: '09_pizza_dinner.jpg', label: 'Dinner', people: 1 },
  { file: '10_stable_father_baby.jpg', label: 'Father & baby', people: 2 },
  { file: '11_wheel_repair.jpg', label: 'Wheel repair', people: 1 },
  { file: '12_frisbee_team.jpg', label: 'Frisbee team', people: 5 },
]

export const sampleUrl = (file) => `/samples/${file}`
